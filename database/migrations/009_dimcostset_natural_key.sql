/*
DimCostSet natural key: one row per (ProjectID, ContractorKey, CostStage).

Re-ingesting the same project / contractor / stage upserts that row in place
(stg.usp_CommitBatch, migration 010), so CostSetKey is stable and there is no
IsCurrent versioning.

Steps:
1. Normalise blank CostStage values to NULL (the commit proc does the same).
2. Backfill ContractorKey on rows committed before contractors were tracked,
   using the SelectedContractor text already stored on the row.
3. Drop single-column unique indexes/constraints on ProjectID or ProjectKey.
4. Add UQ_DimCostSet_Project_Contractor_Stage.
*/
SET ANSI_NULLS ON;
SET QUOTED_IDENTIFIER ON;
GO

IF OBJECT_ID('dbo.DimCostSet', 'U') IS NOT NULL
   AND COL_LENGTH('dbo.DimCostSet', 'CostStage') IS NOT NULL
BEGIN
    UPDATE dbo.DimCostSet
    SET CostStage = NULLIF(LTRIM(RTRIM(CostStage)), N'')
    WHERE CostStage IS NOT NULL
      AND (CostStage <> LTRIM(RTRIM(CostStage)) OR LTRIM(RTRIM(CostStage)) = N'');
END;
GO

IF COL_LENGTH('dbo.DimCostSet', 'SelectedContractor') IS NOT NULL
   AND COL_LENGTH('dbo.DimCostSet', 'ContractorKey') IS NOT NULL
   AND OBJECT_ID('dbo.DimContractor', 'U') IS NOT NULL
BEGIN
    EXEC sp_executesql N'
        INSERT INTO dbo.DimContractor (ContractorName)
        SELECT MIN(LTRIM(RTRIM(cs.SelectedContractor)))
        FROM dbo.DimCostSet cs
        WHERE cs.ContractorKey IS NULL
          AND NULLIF(LTRIM(RTRIM(cs.SelectedContractor)), N'''') IS NOT NULL
          AND NOT EXISTS (
              SELECT 1
              FROM dbo.DimContractor dc
              WHERE UPPER(LTRIM(RTRIM(dc.ContractorName))) = UPPER(LTRIM(RTRIM(cs.SelectedContractor)))
          )
        GROUP BY UPPER(LTRIM(RTRIM(cs.SelectedContractor)));

        UPDATE cs
        SET ContractorKey = k.ContractorKey
        FROM dbo.DimCostSet cs
        CROSS APPLY (
            SELECT MIN(dc.ContractorKey) AS ContractorKey
            FROM dbo.DimContractor dc
            WHERE UPPER(LTRIM(RTRIM(dc.ContractorName))) = UPPER(LTRIM(RTRIM(cs.SelectedContractor)))
        ) AS k
        WHERE cs.ContractorKey IS NULL
          AND k.ContractorKey IS NOT NULL;';
END;
GO

IF OBJECT_ID('dbo.DimCostSet', 'U') IS NOT NULL
BEGIN
    DECLARE @DropSql NVARCHAR(MAX);

    SELECT @DropSql = STRING_AGG(
        CASE
            WHEN i.is_unique_constraint = 1
                THEN N'ALTER TABLE dbo.DimCostSet DROP CONSTRAINT ' + QUOTENAME(i.name) + N';'
            ELSE N'DROP INDEX ' + QUOTENAME(i.name) + N' ON dbo.DimCostSet;'
        END,
        NCHAR(10)
    )
    FROM sys.indexes i
    WHERE i.object_id = OBJECT_ID('dbo.DimCostSet')
      AND i.is_unique = 1
      AND i.is_primary_key = 0
      AND (
          SELECT COUNT(*)
          FROM sys.index_columns ic
          WHERE ic.object_id = i.object_id
            AND ic.index_id = i.index_id
            AND ic.is_included_column = 0
      ) = 1
      AND EXISTS (
          SELECT 1
          FROM sys.index_columns ic
          INNER JOIN sys.columns c
              ON c.object_id = ic.object_id
             AND c.column_id = ic.column_id
          WHERE ic.object_id = i.object_id
            AND ic.index_id = i.index_id
            AND ic.is_included_column = 0
            AND LOWER(c.name) IN (N'projectid', N'projectkey')
      );

    IF @DropSql IS NOT NULL
        EXEC sp_executesql @DropSql;
END;
GO

IF OBJECT_ID('dbo.DimCostSet', 'U') IS NOT NULL
   AND NOT EXISTS (
       SELECT 1
       FROM sys.key_constraints
       WHERE name = 'UQ_DimCostSet_Project_Contractor_Stage'
         AND parent_object_id = OBJECT_ID('dbo.DimCostSet')
   )
BEGIN
    ALTER TABLE dbo.DimCostSet
        ADD CONSTRAINT UQ_DimCostSet_Project_Contractor_Stage
        UNIQUE (ProjectID, ContractorKey, CostStage);
END;
GO
