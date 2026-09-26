-- Minimal DimLocation for usp_CommitBatch (lookup by LocationLabel).
-- DEMO workbook stages LocationLabel = 'North West' (from Region).

IF OBJECT_ID('dbo.DimLocation', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.DimLocation (
        LocationKey INT IDENTITY(1, 1) NOT NULL PRIMARY KEY,
        LocationLabel NVARCHAR(255) NOT NULL
    );
END;
GO

IF NOT EXISTS (
    SELECT 1
    FROM sys.indexes
    WHERE name = 'UX_DimLocation_LocationLabel'
      AND object_id = OBJECT_ID('dbo.DimLocation')
)
BEGIN
    CREATE UNIQUE INDEX UX_DimLocation_LocationLabel
        ON dbo.DimLocation (LocationLabel);
END;
GO

IF NOT EXISTS (
    SELECT 1
    FROM dbo.DimLocation
    WHERE UPPER(LTRIM(RTRIM(LocationLabel))) = UPPER(LTRIM(RTRIM(N'North West')))
)
BEGIN
    INSERT INTO dbo.DimLocation (LocationLabel)
    VALUES (N'North West');
END;
GO
