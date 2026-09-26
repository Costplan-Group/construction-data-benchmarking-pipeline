-- Minimal DimSector for usp_ValidateBatch / usp_CommitBatch.
-- DEMO workbook stages SectorCode = 'Education' (from Sector label).

IF OBJECT_ID('dbo.DimSector', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.DimSector (
        SectorKey INT IDENTITY(1, 1) NOT NULL PRIMARY KEY,
        SectorCode NVARCHAR(50) NOT NULL,
        SectorName NVARCHAR(255) NOT NULL
    );
END;
GO

IF NOT EXISTS (
    SELECT 1
    FROM sys.indexes
    WHERE name = 'UX_DimSector_SectorCode'
      AND object_id = OBJECT_ID('dbo.DimSector')
)
BEGIN
    CREATE UNIQUE INDEX UX_DimSector_SectorCode
        ON dbo.DimSector (SectorCode);
END;
GO

IF NOT EXISTS (
    SELECT 1
    FROM dbo.DimSector
    WHERE UPPER(LTRIM(RTRIM(SectorCode))) = UPPER(LTRIM(RTRIM(N'Education')))
)
BEGIN
    INSERT INTO dbo.DimSector (SectorCode, SectorName)
    VALUES (N'Education', N'Education');
END;
GO
