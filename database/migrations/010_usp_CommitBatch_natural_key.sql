/*
Commit staged workbook data into curated/final tables.

Responsibility:
- ensure the batch exists
- stop commit if blocking validation errors exist
- upsert the project dimension
- insert new contractors, L2 elements and adjustment types (existing dimension rows are never overwritten)
- upsert DimCostSet on its natural key (ProjectID, ContractorKey, CostStage); the MERGE OUTPUT
  supplies CostSetKey, so re-ingesting a project/contractor/stage reuses the same key
- replace project quant, L2 element cost, cost adjustment and cost set summary facts for that key

Cost set summary derivation:
- measuredWorksTotal     = SUM(stg.Level2.TotalCost)
- buildingWorksEstimate  = measured works + adjustments that are neither risk nor inflation
- totalInclRisk          = building works + adjustments whose category/subtype mentions "risk"
- totalInclInflation     = incl. risk + adjustments whose category/subtype mentions "inflation"
- grandTotal             = selected tenderer's FinalAdjustedTenderSum, else totalInclInflation
Adjustments with IncludedInComparison = 0 are excluded from the summary.

Requires migrations 007_warehouse_tables.sql and 009_dimcostset_natural_key.sql.
*/
SET ANSI_NULLS ON;
SET QUOTED_IDENTIFIER ON;
GO

CREATE OR ALTER PROCEDURE stg.usp_CommitBatch
    @LoadBatchID UNIQUEIDENTIFIER
AS
BEGIN
    SET NOCOUNT ON;

    IF NOT EXISTS (
        SELECT 1
        FROM stg.LoadBatch
        WHERE LoadBatchID = @LoadBatchID
    )
    BEGIN
        THROW 50002, 'Load batch not found.', 1;
    END;

    IF EXISTS (
        SELECT 1
        FROM stg.ValidationError
        WHERE LoadBatchID = @LoadBatchID
          AND Severity = 'ERROR'
    )
    BEGIN
        THROW 50003, 'Batch has validation errors and cannot be committed.', 1;
    END;

    /*
    DimProject contract for this environment:
      - ProjectKey (PK)
      - ProjectID (unique)
      - ProjectName, ClientName
      - LocationKey FK, SectorKey FK
      - CreatedAt, UpdatedAt
    */
    IF OBJECT_ID('dbo.DimProject', 'U') IS NULL
    BEGIN
        CREATE TABLE dbo.DimProject (
            ProjectKey INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
            ProjectID VARCHAR(50) NOT NULL,
            ProjectName VARCHAR(250) NOT NULL,
            ClientName VARCHAR(250) NULL,
            LocationKey INT NOT NULL,
            SectorKey INT NOT NULL,
            CreatedAt DATETIME2(0) NOT NULL CONSTRAINT DF_DimProject_CreatedAt DEFAULT (SYSUTCDATETIME()),
            UpdatedAt DATETIME2(0) NOT NULL CONSTRAINT DF_DimProject_UpdatedAt DEFAULT (SYSUTCDATETIME())
        );
        CREATE UNIQUE INDEX UX_DimProject_ProjectID
            ON dbo.DimProject (ProjectID);
    END;

    IF OBJECT_ID('dbo.DimCostSet', 'U') IS NULL
    BEGIN
        CREATE TABLE dbo.DimCostSet (
            CostSetKey INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
            ProjectKey INT NOT NULL,
            ProjectID NVARCHAR(100) NOT NULL,
            LoadBatchID UNIQUEIDENTIFIER NOT NULL,
            ContractorKey INT NULL,
            GIFA DECIMAL(18,2) NULL,
            CostStage NVARCHAR(100) NULL,
            BudgetStage NVARCHAR(100) NULL,
            SelectedContractor NVARCHAR(255) NULL,
            BaseDate DATE NULL,
            Currency NVARCHAR(20) NULL,
            CreatedAt DATETIME2(0) NOT NULL CONSTRAINT DF_DimCostSet_CreatedAt DEFAULT (SYSUTCDATETIME()),
            UpdatedAt DATETIME2(0) NOT NULL CONSTRAINT DF_DimCostSet_UpdatedAt DEFAULT (SYSUTCDATETIME()),
            CONSTRAINT FK_DimCostSet_DimProject
                FOREIGN KEY (ProjectKey) REFERENCES dbo.DimProject (ProjectKey),
            CONSTRAINT UQ_DimCostSet_Project_Contractor_Stage
                UNIQUE (ProjectID, ContractorKey, CostStage)
        );
    END;
    IF OBJECT_ID('dbo.FactProjectQuant', 'U') IS NULL
    BEGIN
        CREATE TABLE dbo.FactProjectQuant (
            FactProjectQuantKey BIGINT IDENTITY(1,1) NOT NULL PRIMARY KEY,
            CostSetKey INT NOT NULL,
            LoadBatchID UNIQUEIDENTIFIER NOT NULL,
            RowNum INT NOT NULL,
            ProjectQuantCode NVARCHAR(100) NULL,
            ProjectQuantName NVARCHAR(255) NULL,
            Qty DECIMAL(18,4) NULL,
            Unit NVARCHAR(50) NULL,
            Comment NVARCHAR(1000) NULL,
            CreatedAt DATETIME2(0) NOT NULL CONSTRAINT DF_FactProjectQuant_CreatedAt DEFAULT (SYSUTCDATETIME()),
            CONSTRAINT FK_FactProjectQuant_DimCostSet
                FOREIGN KEY (CostSetKey) REFERENCES dbo.DimCostSet (CostSetKey)
        );
        CREATE INDEX IX_FactProjectQuant_CostSetKey
            ON dbo.FactProjectQuant (CostSetKey);
        CREATE INDEX IX_FactProjectQuant_LoadBatchID
            ON dbo.FactProjectQuant (LoadBatchID);
    END;

    IF OBJECT_ID('dbo.DimContractor', 'U') IS NULL
        OR OBJECT_ID('dbo.DimElementL2', 'U') IS NULL
        OR OBJECT_ID('dbo.DimAdjustmentType', 'U') IS NULL
        OR OBJECT_ID('dbo.FactElementCostL2', 'U') IS NULL
        OR OBJECT_ID('dbo.FactCostAdjustment', 'U') IS NULL
        OR OBJECT_ID('dbo.FactCostSetSummary', 'U') IS NULL
    BEGIN
        THROW 50012, 'Warehouse tables are missing. Run database/migrate.py (007_warehouse_tables.sql).', 1;
    END;

    BEGIN TRY
        BEGIN TRANSACTION;

        DECLARE
            @ProjectID NVARCHAR(100),
            @ProjectName NVARCHAR(255),
            @ClientName NVARCHAR(255),
            @SectorCode NVARCHAR(50),
            @LocationLabel NVARCHAR(255),
            @GIFA DECIMAL(18,2),
            @CostStage NVARCHAR(100),
            @BudgetStage NVARCHAR(100),
            @SelectedContractor NVARCHAR(255),
            @BaseDate DATE,
            @Currency NVARCHAR(20),
            @SectorKey INT,
            @LocationKey INT,
            @LocationLookupColumn SYSNAME,
            @LocationLookupSql NVARCHAR(MAX),
            @DynamicSql NVARCHAR(MAX),
            @DimProjectProjectKeyCol SYSNAME,
            @DimProjectProjectIDCol SYSNAME,
            @DimProjectProjectNameCol SYSNAME,
            @DimProjectClientNameCol SYSNAME,
            @DimProjectLocationKeyCol SYSNAME,
            @DimProjectSectorKeyCol SYSNAME,
            @DimProjectUpdatedAtCol SYSNAME,
            @DimCostSetCostSetKeyCol SYSNAME,
            @DimCostSetProjectKeyCol SYSNAME,
            @DimCostSetProjectIDCol SYSNAME,
            @DimCostSetSourceCostSetIdentifierCol SYSNAME,
            @DimCostSetLoadBatchIDCol SYSNAME,
            @DimCostSetGIFACol SYSNAME,
            @DimCostSetCostStageCol SYSNAME,
            @DimCostSetBudgetStageCol SYSNAME,
            @DimCostSetDataStatusCol SYSNAME,
            @DimCostSetSelectedContractorCol SYSNAME,
            @DimCostSetBaseDateCol SYSNAME,
            @DimCostSetCurrencyCol SYSNAME,
            @DimCostSetSourceFileCol SYSNAME,
            @DimCostSetUploadedAtCol SYSNAME,
            @DimCostSetIsCurrentCol SYSNAME,
            @DimCostSetContractorKeyCol SYSNAME,
            @DimCostSetUpdatedAtCol SYSNAME,
            @FactProjectQuantCostSetKeyCol SYSNAME,
            @SourceFileValue NVARCHAR(260),
            @ProjectKey INT,
            @CostSetKey INT;

        SELECT TOP 1
            @ProjectID = pi.ProjectID,
            @ProjectName = pi.ProjectName,
            @ClientName = pi.ClientName,
            @SectorCode = pi.SectorCode,
            @LocationLabel = pi.LocationLabel,
            @GIFA = pi.GIFA,
            @CostStage = pi.CostStage,
            @BudgetStage = pi.BudgetStage,
            @SelectedContractor = pi.SelectedContractor,
            @BaseDate = pi.BaseDate,
            @Currency = pi.Currency
        FROM stg.ProjectInformation pi
        WHERE pi.LoadBatchID = @LoadBatchID
        ORDER BY pi.RowNum;

        IF @ProjectID IS NULL
        BEGIN
            THROW 50004, 'Cannot commit batch because ProjectInformation.ProjectID is missing.', 1;
        END;

        SELECT TOP 1
            @SectorKey = ds.SectorKey
        FROM dbo.DimSector ds
        WHERE UPPER(LTRIM(RTRIM(ds.SectorCode))) = UPPER(LTRIM(RTRIM(@SectorCode)));

        IF @SectorKey IS NULL
        BEGIN
            THROW 50005, 'Cannot resolve SectorKey from ProjectInformation.SectorCode.', 1;
        END;

        IF OBJECT_ID('dbo.DimLocation', 'U') IS NULL
        BEGIN
            THROW 50006, 'Cannot commit because dbo.DimLocation does not exist.', 1;
        END;

        -- Resolve key column names early (also used by LocationKey fallback logic).
        SELECT @DimProjectProjectIDCol = c.name
        FROM sys.columns c
        WHERE c.object_id = OBJECT_ID('dbo.DimProject') AND LOWER(c.name) = 'projectid';
        SELECT @DimProjectLocationKeyCol = c.name
        FROM sys.columns c
        WHERE c.object_id = OBJECT_ID('dbo.DimProject') AND LOWER(c.name) = 'locationkey';

        SET @LocationLookupColumn = NULL;
        IF COL_LENGTH('dbo.DimLocation', 'LocationLabel') IS NOT NULL
            SET @LocationLookupColumn = 'LocationLabel';
        ELSE IF COL_LENGTH('dbo.DimLocation', 'LocationName') IS NOT NULL
            SET @LocationLookupColumn = 'LocationName';
        ELSE IF COL_LENGTH('dbo.DimLocation', 'Name') IS NOT NULL
            SET @LocationLookupColumn = 'Name';
        ELSE IF COL_LENGTH('dbo.DimLocation', 'Location') IS NOT NULL
            SET @LocationLookupColumn = 'Location';
        ELSE IF COL_LENGTH('dbo.DimLocation', 'LocationCode') IS NOT NULL
            SET @LocationLookupColumn = 'LocationCode';
        ELSE IF COL_LENGTH('dbo.DimLocation', 'Region') IS NOT NULL
            SET @LocationLookupColumn = 'Region';
        ELSE IF COL_LENGTH('dbo.DimLocation', 'RegionName') IS NOT NULL
            SET @LocationLookupColumn = 'RegionName';
        ELSE IF COL_LENGTH('dbo.DimLocation', 'City') IS NOT NULL
            SET @LocationLookupColumn = 'City';
        ELSE IF COL_LENGTH('dbo.DimLocation', 'CityName') IS NOT NULL
            SET @LocationLookupColumn = 'CityName';

        IF @LocationLookupColumn IS NULL
        BEGIN
            THROW 50007, 'dbo.DimLocation needs one of: LocationLabel, LocationName, Name, Location, LocationCode, Region, RegionName, City, CityName.', 1;
        END;

        SET @LocationLookupSql = N'
            SELECT TOP 1 @OutLocationKey = dl.LocationKey
            FROM dbo.DimLocation dl
            WHERE UPPER(LTRIM(RTRIM(CONVERT(NVARCHAR(255), dl.' + QUOTENAME(@LocationLookupColumn) + N'))))
                = UPPER(LTRIM(RTRIM(@InLocationLabel)));';

        EXEC sp_executesql
            @LocationLookupSql,
            N'@InLocationLabel NVARCHAR(255), @OutLocationKey INT OUTPUT',
            @InLocationLabel = @LocationLabel,
            @OutLocationKey = @LocationKey OUTPUT;

        IF @LocationKey IS NULL
        BEGIN
            -- Fallback for updates: if project already exists, retain its current LocationKey.
            SET @DynamicSql = N'
                SELECT TOP 1 @OutLocationKey = dp.' + QUOTENAME(@DimProjectLocationKeyCol) + N'
                FROM dbo.DimProject dp
                WHERE dp.' + QUOTENAME(@DimProjectProjectIDCol) + N' = @ProjectID;';
            EXEC sp_executesql
                @DynamicSql,
                N'@ProjectID NVARCHAR(100), @OutLocationKey INT OUTPUT',
                @ProjectID = @ProjectID,
                @OutLocationKey = @LocationKey OUTPUT;
        END;

        IF @LocationKey IS NULL
        BEGIN
            THROW 50008, 'Cannot resolve LocationKey from ProjectInformation.LocationLabel.', 1;
        END;

        SELECT @DimProjectProjectKeyCol = c.name
        FROM sys.columns c
        WHERE c.object_id = OBJECT_ID('dbo.DimProject') AND LOWER(c.name) = 'projectkey';
        SELECT @DimProjectProjectIDCol = c.name
        FROM sys.columns c
        WHERE c.object_id = OBJECT_ID('dbo.DimProject') AND LOWER(c.name) = 'projectid';
        SELECT @DimProjectProjectNameCol = c.name
        FROM sys.columns c
        WHERE c.object_id = OBJECT_ID('dbo.DimProject') AND LOWER(c.name) = 'projectname';
        SELECT @DimProjectClientNameCol = c.name
        FROM sys.columns c
        WHERE c.object_id = OBJECT_ID('dbo.DimProject') AND LOWER(c.name) = 'clientname';
        SELECT @DimProjectLocationKeyCol = c.name
        FROM sys.columns c
        WHERE c.object_id = OBJECT_ID('dbo.DimProject') AND LOWER(c.name) = 'locationkey';
        SELECT @DimProjectSectorKeyCol = c.name
        FROM sys.columns c
        WHERE c.object_id = OBJECT_ID('dbo.DimProject') AND LOWER(c.name) = 'sectorkey';
        SELECT @DimProjectUpdatedAtCol = c.name
        FROM sys.columns c
        WHERE c.object_id = OBJECT_ID('dbo.DimProject') AND LOWER(c.name) = 'updatedat';

        IF @DimProjectProjectKeyCol IS NULL OR @DimProjectProjectIDCol IS NULL
            OR @DimProjectProjectNameCol IS NULL OR @DimProjectLocationKeyCol IS NULL
            OR @DimProjectSectorKeyCol IS NULL
        BEGIN
            THROW 50009, 'dbo.DimProject is missing required columns (projectKey/projectID/projectName/locationKey/sectorKey).', 1;
        END;

        SELECT @DimCostSetCostSetKeyCol = c.name
        FROM sys.columns c
        WHERE c.object_id = OBJECT_ID('dbo.DimCostSet') AND LOWER(c.name) = 'costsetkey';
        SELECT @DimCostSetProjectKeyCol = c.name
        FROM sys.columns c
        WHERE c.object_id = OBJECT_ID('dbo.DimCostSet') AND LOWER(c.name) = 'projectkey';
        SELECT @DimCostSetProjectIDCol = c.name
        FROM sys.columns c
        WHERE c.object_id = OBJECT_ID('dbo.DimCostSet') AND LOWER(c.name) = 'projectid';
        SELECT @DimCostSetSourceCostSetIdentifierCol = c.name
        FROM sys.columns c
        WHERE c.object_id = OBJECT_ID('dbo.DimCostSet') AND LOWER(c.name) = 'sourcecostsetidentifier';
        SELECT @DimCostSetLoadBatchIDCol = c.name
        FROM sys.columns c
        WHERE c.object_id = OBJECT_ID('dbo.DimCostSet') AND LOWER(c.name) = 'loadbatchid';
        SELECT @DimCostSetGIFACol = c.name
        FROM sys.columns c
        WHERE c.object_id = OBJECT_ID('dbo.DimCostSet') AND LOWER(c.name) = 'gifa';
        SELECT @DimCostSetCostStageCol = c.name
        FROM sys.columns c
        WHERE c.object_id = OBJECT_ID('dbo.DimCostSet') AND LOWER(c.name) = 'coststage';
        SELECT @DimCostSetBudgetStageCol = c.name
        FROM sys.columns c
        WHERE c.object_id = OBJECT_ID('dbo.DimCostSet') AND LOWER(c.name) = 'budgetstage';
        SELECT @DimCostSetDataStatusCol = c.name
        FROM sys.columns c
        WHERE c.object_id = OBJECT_ID('dbo.DimCostSet') AND LOWER(c.name) = 'datastatus';
        SELECT @DimCostSetSelectedContractorCol = c.name
        FROM sys.columns c
        WHERE c.object_id = OBJECT_ID('dbo.DimCostSet') AND LOWER(c.name) = 'selectedcontractor';
        SELECT @DimCostSetBaseDateCol = c.name
        FROM sys.columns c
        WHERE c.object_id = OBJECT_ID('dbo.DimCostSet') AND LOWER(c.name) = 'basedate';
        SELECT @DimCostSetCurrencyCol = c.name
        FROM sys.columns c
        WHERE c.object_id = OBJECT_ID('dbo.DimCostSet') AND LOWER(c.name) = 'currency';
        SELECT @DimCostSetSourceFileCol = c.name
        FROM sys.columns c
        WHERE c.object_id = OBJECT_ID('dbo.DimCostSet') AND LOWER(c.name) = 'sourcefile';
        SELECT @DimCostSetUploadedAtCol = c.name
        FROM sys.columns c
        WHERE c.object_id = OBJECT_ID('dbo.DimCostSet') AND LOWER(c.name) = 'uploadedat';
        SELECT @DimCostSetIsCurrentCol = c.name
        FROM sys.columns c
        WHERE c.object_id = OBJECT_ID('dbo.DimCostSet') AND LOWER(c.name) = 'iscurrent';
        SELECT @DimCostSetUpdatedAtCol = c.name
        FROM sys.columns c
        WHERE c.object_id = OBJECT_ID('dbo.DimCostSet') AND LOWER(c.name) = 'updatedat';

        SELECT @DimCostSetContractorKeyCol = c.name
        FROM sys.columns c
        WHERE c.object_id = OBJECT_ID('dbo.DimCostSet') AND LOWER(c.name) = 'contractorkey';

        IF @DimCostSetCostSetKeyCol IS NULL OR @DimCostSetProjectKeyCol IS NULL
            OR @DimCostSetProjectIDCol IS NULL OR @DimCostSetContractorKeyCol IS NULL
            OR @DimCostSetCostStageCol IS NULL
        BEGIN
            THROW 50010, 'dbo.DimCostSet is missing required columns (costSetKey/projectKey/projectID/contractorKey/costStage).', 1;
        END;

        SELECT @FactProjectQuantCostSetKeyCol = c.name
        FROM sys.columns c
        WHERE c.object_id = OBJECT_ID('dbo.FactProjectQuant') AND LOWER(c.name) = 'costsetkey';

        IF @FactProjectQuantCostSetKeyCol IS NULL
        BEGIN
            THROW 50011, 'dbo.FactProjectQuant is missing required column costSetKey.', 1;
        END;

        SET @DynamicSql = N'
        MERGE dbo.DimProject AS tgt
        USING (
            SELECT
                @ProjectID AS ProjectID,
                @ProjectName AS ProjectName,
                @ClientName AS ClientName,
                @LocationKey AS LocationKey,
                @SectorKey AS SectorKey
        ) AS src
            ON tgt.' + QUOTENAME(@DimProjectProjectIDCol) + N' = src.ProjectID
        WHEN MATCHED THEN
            UPDATE SET
                tgt.' + QUOTENAME(@DimProjectProjectNameCol) + N' = src.ProjectName,' +
                CASE WHEN @DimProjectClientNameCol IS NOT NULL THEN N' tgt.' + QUOTENAME(@DimProjectClientNameCol) + N' = src.ClientName,' ELSE N'' END +
                N' tgt.' + QUOTENAME(@DimProjectLocationKeyCol) + N' = src.LocationKey,
                tgt.' + QUOTENAME(@DimProjectSectorKeyCol) + N' = src.SectorKey' +
                CASE WHEN @DimProjectUpdatedAtCol IS NOT NULL THEN N', tgt.' + QUOTENAME(@DimProjectUpdatedAtCol) + N' = SYSUTCDATETIME()' ELSE N'' END + N'
        WHEN NOT MATCHED THEN
            INSERT (' + QUOTENAME(@DimProjectProjectIDCol) + N', ' + QUOTENAME(@DimProjectProjectNameCol) +
                CASE WHEN @DimProjectClientNameCol IS NOT NULL THEN N', ' + QUOTENAME(@DimProjectClientNameCol) ELSE N'' END +
                N', ' + QUOTENAME(@DimProjectLocationKeyCol) + N', ' + QUOTENAME(@DimProjectSectorKeyCol) + N')
            VALUES (
                src.ProjectID,
                src.ProjectName' +
                CASE WHEN @DimProjectClientNameCol IS NOT NULL THEN N', src.ClientName' ELSE N'' END +
                N', src.LocationKey, src.SectorKey
            );';

        EXEC sp_executesql
            @DynamicSql,
            N'@ProjectID NVARCHAR(100), @ProjectName NVARCHAR(255), @ClientName NVARCHAR(255), @LocationKey INT, @SectorKey INT',
            @ProjectID = @ProjectID,
            @ProjectName = @ProjectName,
            @ClientName = @ClientName,
            @LocationKey = @LocationKey,
            @SectorKey = @SectorKey;

        SET @DynamicSql = N'
            SELECT TOP 1 @OutProjectKey = dp.' + QUOTENAME(@DimProjectProjectKeyCol) + N'
            FROM dbo.DimProject dp
            WHERE dp.' + QUOTENAME(@DimProjectProjectIDCol) + N' = @ProjectID;';
        EXEC sp_executesql
            @DynamicSql,
            N'@ProjectID NVARCHAR(100), @OutProjectKey INT OUTPUT',
            @ProjectID = @ProjectID,
            @OutProjectKey = @ProjectKey OUTPUT;

        /* ---------- Contractors (resolved first: ContractorKey is part of the cost set key) ---------- */
        DECLARE
            @SelectedContractorName NVARCHAR(255),
            @ContractorKey INT;

        SELECT TOP 1
            @SelectedContractorName = LTRIM(RTRIM(COALESCE(NULLIF(LTRIM(RTRIM(pt.TendererName)), N''), pt.TendererLabel)))
        FROM stg.ProjectTenderer pt
        WHERE pt.LoadBatchID = @LoadBatchID
          AND pt.IsSelected = 1
        ORDER BY pt.RowNum;

        SET @SelectedContractorName = COALESCE(
            NULLIF(@SelectedContractorName, N''),
            NULLIF(LTRIM(RTRIM(@SelectedContractor)), N'')
        );

        INSERT INTO dbo.DimContractor (ContractorName)
        SELECT MIN(src.ContractorName)
        FROM (
            SELECT LTRIM(RTRIM(COALESCE(NULLIF(LTRIM(RTRIM(pt.TendererName)), N''), pt.TendererLabel))) AS ContractorName
            FROM stg.ProjectTenderer pt
            WHERE pt.LoadBatchID = @LoadBatchID
            UNION
            SELECT @SelectedContractorName
        ) AS src
        WHERE NULLIF(src.ContractorName, N'') IS NOT NULL
          AND NOT EXISTS (
              SELECT 1
              FROM dbo.DimContractor dc WITH (UPDLOCK, HOLDLOCK)
              WHERE UPPER(LTRIM(RTRIM(dc.ContractorName))) = UPPER(src.ContractorName)
          )
        GROUP BY UPPER(src.ContractorName);

        SELECT @ContractorKey = MIN(dc.ContractorKey)
        FROM dbo.DimContractor dc
        WHERE UPPER(LTRIM(RTRIM(dc.ContractorName))) = UPPER(@SelectedContractorName);

        SET @CostStage = NULLIF(LTRIM(RTRIM(@CostStage)), N'');

        /* ---------- Cost set: upsert on (ProjectID, ContractorKey, CostStage) ---------- */
        SET @DynamicSql = N'
        DECLARE @Keys TABLE (CostSetKey INT NOT NULL);

        MERGE dbo.DimCostSet WITH (HOLDLOCK) AS tgt
        USING (
            SELECT
                @ProjectKey AS ProjectKey,
                @ProjectID AS ProjectID,
                @ContractorKey AS ContractorKey,
                @GIFA AS GIFA,
                @CostStage AS CostStage,
                @BudgetStage AS BudgetStage,
                @DataStatus AS DataStatus,
                @SourceCostSetIdentifier AS SourceCostSetIdentifier,
                @SourceFile AS SourceFile,
                @SelectedContractor AS SelectedContractor,
                @BaseDate AS BaseDate,
                @Currency AS Currency
        ) AS src
            ON tgt.' + QUOTENAME(@DimCostSetProjectIDCol) + N' = src.ProjectID
           AND (tgt.' + QUOTENAME(@DimCostSetContractorKeyCol) + N' = src.ContractorKey
                OR (tgt.' + QUOTENAME(@DimCostSetContractorKeyCol) + N' IS NULL AND src.ContractorKey IS NULL))
           AND (tgt.' + QUOTENAME(@DimCostSetCostStageCol) + N' = src.CostStage
                OR (tgt.' + QUOTENAME(@DimCostSetCostStageCol) + N' IS NULL AND src.CostStage IS NULL))
        WHEN MATCHED THEN
            UPDATE SET
                tgt.' + QUOTENAME(@DimCostSetProjectKeyCol) + N' = src.ProjectKey' +
                CASE WHEN @DimCostSetLoadBatchIDCol IS NOT NULL THEN N', tgt.' + QUOTENAME(@DimCostSetLoadBatchIDCol) + N' = @LoadBatchID' ELSE N'' END +
                CASE WHEN @DimCostSetSourceCostSetIdentifierCol IS NOT NULL THEN N', tgt.' + QUOTENAME(@DimCostSetSourceCostSetIdentifierCol) + N' = src.SourceCostSetIdentifier' ELSE N'' END +
                CASE WHEN @DimCostSetGIFACol IS NOT NULL THEN N', tgt.' + QUOTENAME(@DimCostSetGIFACol) + N' = src.GIFA' ELSE N'' END +
                CASE WHEN @DimCostSetBudgetStageCol IS NOT NULL THEN N', tgt.' + QUOTENAME(@DimCostSetBudgetStageCol) + N' = src.BudgetStage' ELSE N'' END +
                CASE WHEN @DimCostSetDataStatusCol IS NOT NULL THEN N', tgt.' + QUOTENAME(@DimCostSetDataStatusCol) + N' = src.DataStatus' ELSE N'' END +
                CASE WHEN @DimCostSetSourceFileCol IS NOT NULL THEN N', tgt.' + QUOTENAME(@DimCostSetSourceFileCol) + N' = src.SourceFile' ELSE N'' END +
                CASE WHEN @DimCostSetUploadedAtCol IS NOT NULL THEN N', tgt.' + QUOTENAME(@DimCostSetUploadedAtCol) + N' = SYSUTCDATETIME()' ELSE N'' END +
                CASE WHEN @DimCostSetSelectedContractorCol IS NOT NULL THEN N', tgt.' + QUOTENAME(@DimCostSetSelectedContractorCol) + N' = src.SelectedContractor' ELSE N'' END +
                CASE WHEN @DimCostSetBaseDateCol IS NOT NULL THEN N', tgt.' + QUOTENAME(@DimCostSetBaseDateCol) + N' = src.BaseDate' ELSE N'' END +
                CASE WHEN @DimCostSetCurrencyCol IS NOT NULL THEN N', tgt.' + QUOTENAME(@DimCostSetCurrencyCol) + N' = src.Currency' ELSE N'' END +
                CASE WHEN @DimCostSetUpdatedAtCol IS NOT NULL THEN N', tgt.' + QUOTENAME(@DimCostSetUpdatedAtCol) + N' = SYSUTCDATETIME()' ELSE N'' END + N'
        WHEN NOT MATCHED THEN
            INSERT (' + QUOTENAME(@DimCostSetProjectKeyCol) +
                N', ' + QUOTENAME(@DimCostSetProjectIDCol) +
                N', ' + QUOTENAME(@DimCostSetContractorKeyCol) +
                CASE WHEN @DimCostSetSourceCostSetIdentifierCol IS NOT NULL THEN N', ' + QUOTENAME(@DimCostSetSourceCostSetIdentifierCol) ELSE N'' END +
                CASE WHEN @DimCostSetLoadBatchIDCol IS NOT NULL THEN N', ' + QUOTENAME(@DimCostSetLoadBatchIDCol) ELSE N'' END +
                CASE WHEN @DimCostSetGIFACol IS NOT NULL THEN N', ' + QUOTENAME(@DimCostSetGIFACol) ELSE N'' END +
                CASE WHEN @DimCostSetCostStageCol IS NOT NULL THEN N', ' + QUOTENAME(@DimCostSetCostStageCol) ELSE N'' END +
                CASE WHEN @DimCostSetBudgetStageCol IS NOT NULL THEN N', ' + QUOTENAME(@DimCostSetBudgetStageCol) ELSE N'' END +
                CASE WHEN @DimCostSetDataStatusCol IS NOT NULL THEN N', ' + QUOTENAME(@DimCostSetDataStatusCol) ELSE N'' END +
                CASE WHEN @DimCostSetSourceFileCol IS NOT NULL THEN N', ' + QUOTENAME(@DimCostSetSourceFileCol) ELSE N'' END +
                CASE WHEN @DimCostSetUploadedAtCol IS NOT NULL THEN N', ' + QUOTENAME(@DimCostSetUploadedAtCol) ELSE N'' END +
                CASE WHEN @DimCostSetSelectedContractorCol IS NOT NULL THEN N', ' + QUOTENAME(@DimCostSetSelectedContractorCol) ELSE N'' END +
                CASE WHEN @DimCostSetBaseDateCol IS NOT NULL THEN N', ' + QUOTENAME(@DimCostSetBaseDateCol) ELSE N'' END +
                CASE WHEN @DimCostSetCurrencyCol IS NOT NULL THEN N', ' + QUOTENAME(@DimCostSetCurrencyCol) ELSE N'' END +
                CASE WHEN @DimCostSetIsCurrentCol IS NOT NULL THEN N', ' + QUOTENAME(@DimCostSetIsCurrentCol) ELSE N'' END + N')
            VALUES (
                src.ProjectKey, src.ProjectID, src.ContractorKey' +
                CASE WHEN @DimCostSetSourceCostSetIdentifierCol IS NOT NULL THEN N', src.SourceCostSetIdentifier' ELSE N'' END +
                CASE WHEN @DimCostSetLoadBatchIDCol IS NOT NULL THEN N', @LoadBatchID' ELSE N'' END +
                CASE WHEN @DimCostSetGIFACol IS NOT NULL THEN N', src.GIFA' ELSE N'' END +
                CASE WHEN @DimCostSetCostStageCol IS NOT NULL THEN N', src.CostStage' ELSE N'' END +
                CASE WHEN @DimCostSetBudgetStageCol IS NOT NULL THEN N', src.BudgetStage' ELSE N'' END +
                CASE WHEN @DimCostSetDataStatusCol IS NOT NULL THEN N', src.DataStatus' ELSE N'' END +
                CASE WHEN @DimCostSetSourceFileCol IS NOT NULL THEN N', src.SourceFile' ELSE N'' END +
                CASE WHEN @DimCostSetUploadedAtCol IS NOT NULL THEN N', SYSUTCDATETIME()' ELSE N'' END +
                CASE WHEN @DimCostSetSelectedContractorCol IS NOT NULL THEN N', src.SelectedContractor' ELSE N'' END +
                CASE WHEN @DimCostSetBaseDateCol IS NOT NULL THEN N', src.BaseDate' ELSE N'' END +
                CASE WHEN @DimCostSetCurrencyCol IS NOT NULL THEN N', src.Currency' ELSE N'' END +
                CASE WHEN @DimCostSetIsCurrentCol IS NOT NULL THEN N', 1' ELSE N'' END + N'
            )
        OUTPUT inserted.' + QUOTENAME(@DimCostSetCostSetKeyCol) + N' INTO @Keys (CostSetKey);

        SELECT TOP 1 @OutCostSetKey = CostSetKey FROM @Keys;';

        SET @SourceFileValue = N'upload:' + CONVERT(NVARCHAR(36), @LoadBatchID);

        EXEC sp_executesql
            @DynamicSql,
            N'@ProjectKey INT, @ProjectID NVARCHAR(100), @ContractorKey INT, @LoadBatchID UNIQUEIDENTIFIER, @GIFA DECIMAL(18,2), @CostStage NVARCHAR(100), @BudgetStage NVARCHAR(100), @DataStatus NVARCHAR(100), @SourceCostSetIdentifier NVARCHAR(255), @SourceFile NVARCHAR(260), @SelectedContractor NVARCHAR(255), @BaseDate DATE, @Currency NVARCHAR(20), @OutCostSetKey INT OUTPUT',
            @ProjectKey = @ProjectKey,
            @ProjectID = @ProjectID,
            @ContractorKey = @ContractorKey,
            @LoadBatchID = @LoadBatchID,
            @GIFA = @GIFA,
            @CostStage = @CostStage,
            @BudgetStage = @BudgetStage,
            @DataStatus = N'ACTIVE',
            @SourceCostSetIdentifier = @ProjectID,
            @SourceFile = @SourceFileValue,
            @SelectedContractor = @SelectedContractor,
            @BaseDate = @BaseDate,
            @Currency = @Currency,
            @OutCostSetKey = @CostSetKey OUTPUT;

        IF @CostSetKey IS NULL
        BEGIN
            THROW 50013, 'DimCostSet MERGE did not return a CostSetKey.', 1;
        END;

        SET @DynamicSql = N'
            DELETE FROM dbo.FactProjectQuant
            WHERE ' + QUOTENAME(@FactProjectQuantCostSetKeyCol) + N' = @CostSetKey;';
        EXEC sp_executesql
            @DynamicSql,
            N'@CostSetKey INT',
            @CostSetKey = @CostSetKey;

        INSERT INTO dbo.FactProjectQuant (
            CostSetKey,
            LoadBatchID,
            RowNum,
            ProjectQuantCode,
            ProjectQuantName,
            Qty,
            Unit,
            Comment
        )
        SELECT
            @CostSetKey AS CostSetKey,
            @LoadBatchID AS LoadBatchID,
            pq.RowNum,
            pq.ProjectQuantCode,
            pq.ProjectQuantName,
            pq.Qty,
            pq.Unit,
            pq.Comment
        FROM stg.ProjectQuants pq
        WHERE pq.LoadBatchID = @LoadBatchID;

        /* ---------- L2 elements and element costs ---------- */
        ;WITH ElementSource AS (
            SELECT
                LTRIM(RTRIM(l2.L2Code)) AS L2Code,
                NULLIF(LTRIM(RTRIM(l2.L2Name)), N'') AS L2Name,
                NULLIF(LTRIM(RTRIM(l2.L1Code)), N'') AS L1Code,
                NULLIF(LTRIM(RTRIM(l2.L1Name)), N'') AS L1Name,
                ROW_NUMBER() OVER (
                    PARTITION BY UPPER(LTRIM(RTRIM(l2.L2Code)))
                    ORDER BY l2.RowNum
                ) AS rn
            FROM stg.Level2 l2
            WHERE l2.LoadBatchID = @LoadBatchID
              AND NULLIF(LTRIM(RTRIM(l2.L2Code)), N'') IS NOT NULL
        )
        INSERT INTO dbo.DimElementL2 (L1Code, L1Name, L2Code, L2Name)
        SELECT s.L1Code, s.L1Name, s.L2Code, s.L2Name
        FROM ElementSource s
        WHERE s.rn = 1
          AND NOT EXISTS (
              SELECT 1
              FROM dbo.DimElementL2 e WITH (UPDLOCK, HOLDLOCK)
              WHERE UPPER(LTRIM(RTRIM(e.L2Code))) = UPPER(s.L2Code)
          );

        DELETE FROM dbo.FactElementCostL2
        WHERE costSetKey = @CostSetKey;

        INSERT INTO dbo.FactElementCostL2 (costSetKey, elementL2Key, TotalCost)
        SELECT
            @CostSetKey,
            ek.ElementL2Key,
            SUM(l2.TotalCost)
        FROM stg.Level2 l2
        INNER JOIN (
            SELECT
                UPPER(LTRIM(RTRIM(e.L2Code))) AS CodeKey,
                MIN(e.ElementL2Key) AS ElementL2Key
            FROM dbo.DimElementL2 e
            GROUP BY UPPER(LTRIM(RTRIM(e.L2Code)))
        ) AS ek
            ON ek.CodeKey = UPPER(LTRIM(RTRIM(l2.L2Code)))
        WHERE l2.LoadBatchID = @LoadBatchID
        GROUP BY ek.ElementL2Key;

        /* ---------- Adjustment types and adjustments ---------- */
        INSERT INTO dbo.DimAdjustmentType (AdjCategory, AdjSubType)
        SELECT MIN(src.AdjCategory), MIN(src.AdjSubType)
        FROM (
            SELECT
                NULLIF(LTRIM(RTRIM(a.AdjCategory)), N'') AS AdjCategory,
                NULLIF(LTRIM(RTRIM(a.AdjSubType)), N'') AS AdjSubType
            FROM stg.Adjustments a
            WHERE a.LoadBatchID = @LoadBatchID
        ) AS src
        WHERE (src.AdjCategory IS NOT NULL OR src.AdjSubType IS NOT NULL)
          AND NOT EXISTS (
              SELECT 1
              FROM dbo.DimAdjustmentType t WITH (UPDLOCK, HOLDLOCK)
              WHERE ISNULL(UPPER(LTRIM(RTRIM(t.AdjCategory))), N'') = ISNULL(UPPER(src.AdjCategory), N'')
                AND ISNULL(UPPER(LTRIM(RTRIM(t.AdjSubType))), N'') = ISNULL(UPPER(src.AdjSubType), N'')
          )
        GROUP BY ISNULL(UPPER(src.AdjCategory), N''), ISNULL(UPPER(src.AdjSubType), N'');

        DELETE FROM dbo.FactCostAdjustment
        WHERE CostSetKey = @CostSetKey;

        INSERT INTO dbo.FactCostAdjustment (
            CostSetKey,
            adjustmentTypeKey,
            Amount,
            Method,
            RatePercent,
            appliedToBase,
            includedInComparison
        )
        SELECT
            @CostSetKey,
            tk.AdjustmentTypeKey,
            a.Amount,
            a.Method,
            a.RatePercent,
            a.AppliedToBase,
            a.IncludedInComparison
        FROM stg.Adjustments a
        INNER JOIN (
            SELECT
                ISNULL(UPPER(LTRIM(RTRIM(t.AdjCategory))), N'') AS CategoryKey,
                ISNULL(UPPER(LTRIM(RTRIM(t.AdjSubType))), N'') AS SubTypeKey,
                MIN(t.AdjustmentTypeKey) AS AdjustmentTypeKey
            FROM dbo.DimAdjustmentType t
            GROUP BY
                ISNULL(UPPER(LTRIM(RTRIM(t.AdjCategory))), N''),
                ISNULL(UPPER(LTRIM(RTRIM(t.AdjSubType))), N'')
        ) AS tk
            ON tk.CategoryKey = ISNULL(UPPER(LTRIM(RTRIM(a.AdjCategory))), N'')
           AND tk.SubTypeKey = ISNULL(UPPER(LTRIM(RTRIM(a.AdjSubType))), N'')
        WHERE a.LoadBatchID = @LoadBatchID
          AND (
              NULLIF(LTRIM(RTRIM(a.AdjCategory)), N'') IS NOT NULL
              OR NULLIF(LTRIM(RTRIM(a.AdjSubType)), N'') IS NOT NULL
          );

        /* ---------- Cost set summary ---------- */
        DECLARE
            @MeasuredWorks DECIMAL(18,2),
            @OtherAdjustments DECIMAL(18,2),
            @RiskAdjustments DECIMAL(18,2),
            @InflationAdjustments DECIMAL(18,2),
            @FinalAdjustedTenderSum DECIMAL(18,2),
            @BuildingWorks DECIMAL(18,2),
            @TotalInclRisk DECIMAL(18,2),
            @TotalInclInflation DECIMAL(18,2);

        SELECT @MeasuredWorks = SUM(l2.TotalCost)
        FROM stg.Level2 l2
        WHERE l2.LoadBatchID = @LoadBatchID;

        SELECT
            @RiskAdjustments = SUM(CASE WHEN k.Kind = 'RISK' THEN a.Amount END),
            @InflationAdjustments = SUM(CASE WHEN k.Kind = 'INFLATION' THEN a.Amount END),
            @OtherAdjustments = SUM(CASE WHEN k.Kind = 'OTHER' THEN a.Amount END)
        FROM stg.Adjustments a
        CROSS APPLY (
            SELECT CASE
                WHEN LOWER(CONCAT(a.AdjCategory, N' ', a.AdjSubType)) LIKE N'%risk%' THEN 'RISK'
                WHEN LOWER(CONCAT(a.AdjCategory, N' ', a.AdjSubType)) LIKE N'%inflation%' THEN 'INFLATION'
                ELSE 'OTHER'
            END AS Kind
        ) AS k
        WHERE a.LoadBatchID = @LoadBatchID
          AND ISNULL(a.IncludedInComparison, 1) = 1;

        SELECT TOP 1 @FinalAdjustedTenderSum = pt.FinalAdjustedTenderSum
        FROM stg.ProjectTenderer pt
        WHERE pt.LoadBatchID = @LoadBatchID
          AND (
              pt.IsSelected = 1
              OR UPPER(LTRIM(RTRIM(COALESCE(NULLIF(LTRIM(RTRIM(pt.TendererName)), N''), pt.TendererLabel))))
                 = UPPER(@SelectedContractorName)
          )
        ORDER BY pt.IsSelected DESC, pt.RowNum;

        SET @BuildingWorks = @MeasuredWorks + ISNULL(@OtherAdjustments, 0);
        SET @TotalInclRisk = @BuildingWorks + ISNULL(@RiskAdjustments, 0);
        SET @TotalInclInflation = @TotalInclRisk + ISNULL(@InflationAdjustments, 0);

        DELETE FROM dbo.FactCostSetSummary
        WHERE costSetKey = @CostSetKey;

        IF @MeasuredWorks IS NOT NULL OR @FinalAdjustedTenderSum IS NOT NULL
        BEGIN
            INSERT INTO dbo.FactCostSetSummary (
                costSetKey,
                measuredWorksTotal,
                buildingWorksEstimate,
                totalInclRisk,
                totalInclInflation,
                grandTotal
            )
            VALUES (
                @CostSetKey,
                @MeasuredWorks,
                @BuildingWorks,
                @TotalInclRisk,
                @TotalInclInflation,
                COALESCE(@FinalAdjustedTenderSum, @TotalInclInflation)
            );
        END;

        COMMIT TRANSACTION;
    END TRY
    BEGIN CATCH
        IF @@TRANCOUNT > 0
            ROLLBACK TRANSACTION;
        THROW;
    END CATCH;
END;
GO
