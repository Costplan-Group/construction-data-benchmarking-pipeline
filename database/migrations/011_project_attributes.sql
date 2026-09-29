/*
Project attributes captured on the Project Information sheet:
SpecLevel, SiteType, NrOfStoreys, TotalHeightGroundToRoof, BasementArea,
BasementHeight, ComplexityRating, AccessConstraints, Occupied.

Added to stg.ProjectInformation (staged per batch) and dbo.DimProject
(written by stg.usp_CommitBatch, migration 012).
*/
SET ANSI_NULLS ON;
SET QUOTED_IDENTIFIER ON;
GO

DECLARE @Columns TABLE (ColumnName SYSNAME NOT NULL, ColumnType NVARCHAR(100) NOT NULL);
INSERT INTO @Columns (ColumnName, ColumnType)
VALUES
    (N'SpecLevel', N'NVARCHAR(100) NULL'),
    (N'SiteType', N'NVARCHAR(100) NULL'),
    (N'NrOfStoreys', N'INT NULL'),
    (N'TotalHeightGroundToRoof', N'DECIMAL(9,2) NULL'),
    (N'BasementArea', N'DECIMAL(18,2) NULL'),
    (N'BasementHeight', N'DECIMAL(9,2) NULL'),
    (N'ComplexityRating', N'NVARCHAR(100) NULL'),
    (N'AccessConstraints', N'NVARCHAR(500) NULL'),
    (N'Occupied', N'BIT NULL');

DECLARE @Sql NVARCHAR(MAX);

SELECT @Sql = STRING_AGG(
    CONVERT(NVARCHAR(MAX), N'ALTER TABLE ' + t.TableName + N' ADD ' + QUOTENAME(c.ColumnName) + N' ' + c.ColumnType + N';'),
    NCHAR(10)
)
FROM @Columns c
CROSS JOIN (VALUES (N'stg.ProjectInformation'), (N'dbo.DimProject')) AS t (TableName)
WHERE OBJECT_ID(t.TableName, 'U') IS NOT NULL
  AND COL_LENGTH(t.TableName, c.ColumnName) IS NULL;

IF @Sql IS NOT NULL
    EXEC sp_executesql @Sql;
GO
