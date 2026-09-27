/*
Warehouse dimensions and facts populated by stg.usp_CommitBatch.

Creates (if missing):
- dbo.DimProject, dbo.DimCostSet, dbo.FactProjectQuant (previously created lazily by the proc)
- dbo.DimContractor, dbo.DimElementL2, dbo.DimAdjustmentType
- dbo.FactElementCostL2, dbo.FactCostAdjustment, dbo.FactCostSetSummary
- dbo.DimCostSet.ContractorKey

Column names match database/schema/002_reporting_views.sql so existing warehouses
that already have these tables are left untouched.
*/
SET ANSI_NULLS ON;
SET QUOTED_IDENTIFIER ON;
GO

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
GO

IF OBJECT_ID('dbo.DimContractor', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.DimContractor (
        ContractorKey INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
        ContractorName NVARCHAR(255) NOT NULL,
        IsActive BIT NOT NULL CONSTRAINT DF_DimContractor_IsActive DEFAULT (1),
        CreatedAt DATETIME2(0) NOT NULL CONSTRAINT DF_DimContractor_CreatedAt DEFAULT (SYSUTCDATETIME())
    );
    CREATE UNIQUE INDEX UX_DimContractor_ContractorName
        ON dbo.DimContractor (ContractorName);
END;
GO

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
        CONSTRAINT FK_DimCostSet_DimContractor
            FOREIGN KEY (ContractorKey) REFERENCES dbo.DimContractor (ContractorKey)
    );
    CREATE UNIQUE INDEX UX_DimCostSet_ProjectID
        ON dbo.DimCostSet (ProjectID);
END;
GO

IF COL_LENGTH('dbo.DimCostSet', 'ContractorKey') IS NULL
BEGIN
    ALTER TABLE dbo.DimCostSet ADD ContractorKey INT NULL;
END;
GO

IF NOT EXISTS (
    SELECT 1
    FROM sys.foreign_keys fk
    INNER JOIN sys.foreign_key_columns fkc
        ON fkc.constraint_object_id = fk.object_id
    WHERE fk.parent_object_id = OBJECT_ID('dbo.DimCostSet')
      AND fk.referenced_object_id = OBJECT_ID('dbo.DimContractor')
)
BEGIN
    ALTER TABLE dbo.DimCostSet ADD CONSTRAINT FK_DimCostSet_DimContractor
        FOREIGN KEY (ContractorKey) REFERENCES dbo.DimContractor (ContractorKey);
END;
GO

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
GO

IF OBJECT_ID('dbo.DimElementL2', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.DimElementL2 (
        ElementL2Key INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
        L1Code NVARCHAR(50) NULL,
        L1Name NVARCHAR(255) NULL,
        L2Code NVARCHAR(100) NOT NULL,
        L2Name NVARCHAR(255) NULL,
        IsActive BIT NOT NULL CONSTRAINT DF_DimElementL2_IsActive DEFAULT (1),
        CreatedAt DATETIME2(0) NOT NULL CONSTRAINT DF_DimElementL2_CreatedAt DEFAULT (SYSUTCDATETIME()),
        UpdatedAt DATETIME2(0) NOT NULL CONSTRAINT DF_DimElementL2_UpdatedAt DEFAULT (SYSUTCDATETIME())
    );
    CREATE UNIQUE INDEX UX_DimElementL2_L2Code
        ON dbo.DimElementL2 (L2Code);
END;
GO

IF OBJECT_ID('dbo.DimAdjustmentType', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.DimAdjustmentType (
        AdjustmentTypeKey INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
        AdjCategory NVARCHAR(100) NULL,
        AdjSubType NVARCHAR(100) NULL,
        CreatedAt DATETIME2(0) NOT NULL CONSTRAINT DF_DimAdjustmentType_CreatedAt DEFAULT (SYSUTCDATETIME())
    );
    CREATE UNIQUE INDEX UX_DimAdjustmentType_CategorySubType
        ON dbo.DimAdjustmentType (AdjCategory, AdjSubType);
END;
GO

IF OBJECT_ID('dbo.FactElementCostL2', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.FactElementCostL2 (
        FactElementCostL2Key BIGINT IDENTITY(1,1) NOT NULL PRIMARY KEY,
        costSetKey INT NOT NULL,
        elementL2Key INT NOT NULL,
        TotalCost DECIMAL(18,2) NOT NULL,
        Comment NVARCHAR(1000) NULL,
        CreatedAt DATETIME2(0) NOT NULL CONSTRAINT DF_FactElementCostL2_CreatedAt DEFAULT (SYSUTCDATETIME()),
        CONSTRAINT FK_FactElementCostL2_DimCostSet
            FOREIGN KEY (costSetKey) REFERENCES dbo.DimCostSet (CostSetKey),
        CONSTRAINT FK_FactElementCostL2_DimElementL2
            FOREIGN KEY (elementL2Key) REFERENCES dbo.DimElementL2 (ElementL2Key)
    );
    CREATE UNIQUE INDEX UX_FactElementCostL2_CostSet_Element
        ON dbo.FactElementCostL2 (costSetKey, elementL2Key);
END;
GO

IF OBJECT_ID('dbo.FactCostAdjustment', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.FactCostAdjustment (
        FactCostAdjustmentKey BIGINT IDENTITY(1,1) NOT NULL PRIMARY KEY,
        CostSetKey INT NOT NULL,
        adjustmentTypeKey INT NOT NULL,
        Amount DECIMAL(18,2) NULL,
        Method NVARCHAR(50) NULL,
        RatePercent DECIMAL(18,4) NULL,
        appliedToBase BIT NULL,
        includedInComparison BIT NULL,
        CreatedAt DATETIME2(0) NOT NULL CONSTRAINT DF_FactCostAdjustment_CreatedAt DEFAULT (SYSUTCDATETIME()),
        CONSTRAINT FK_FactCostAdjustment_DimCostSet
            FOREIGN KEY (CostSetKey) REFERENCES dbo.DimCostSet (CostSetKey),
        CONSTRAINT FK_FactCostAdjustment_DimAdjustmentType
            FOREIGN KEY (adjustmentTypeKey) REFERENCES dbo.DimAdjustmentType (AdjustmentTypeKey)
    );
    CREATE INDEX IX_FactCostAdjustment_CostSetKey
        ON dbo.FactCostAdjustment (CostSetKey);
END;
GO

IF OBJECT_ID('dbo.FactCostSetSummary', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.FactCostSetSummary (
        costSetKey INT NOT NULL PRIMARY KEY,
        measuredWorksTotal DECIMAL(18,2) NULL,
        buildingWorksEstimate DECIMAL(18,2) NULL,
        totalInclRisk DECIMAL(18,2) NULL,
        totalInclInflation DECIMAL(18,2) NULL,
        grandTotal DECIMAL(18,2) NULL,
        CreatedAt DATETIME2(0) NOT NULL CONSTRAINT DF_FactCostSetSummary_CreatedAt DEFAULT (SYSUTCDATETIME()),
        CONSTRAINT FK_FactCostSetSummary_DimCostSet
            FOREIGN KEY (costSetKey) REFERENCES dbo.DimCostSet (CostSetKey)
    );
END;
GO
