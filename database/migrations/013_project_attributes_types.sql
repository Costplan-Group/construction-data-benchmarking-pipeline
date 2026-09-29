/*
Tighten the project attribute columns added in 011 and move the site flags onto DimProject.

On stg.ProjectInformation and dbo.DimProject:
- SpecLevel        VARCHAR(10)   Low / Medium / High
- SiteType         VARCHAR(20)   Greenfield / Brownfield
- ComplexityRating TINYINT       1-5
- TotalHeightGroundToRoof, BasementArea, BasementHeight DECIMAL(18,4)
Existing values are canonicalised first; anything outside the allowed domain becomes NULL
so the ALTERs cannot fail on old data.

On dbo.DimProject only:
- CHECK constraints for the three domains above
- site flags Demolition, NewBuild, Refurbishment, HorizontalExtension, VerticalExtension,
  Basement, Asbestos, Contamination (BIT NULL), written by stg.usp_CommitBatch (migration 014)
*/
SET ANSI_NULLS ON;
SET QUOTED_IDENTIFIER ON;
GO

DECLARE @Tables TABLE (TableName NVARCHAR(128) NOT NULL);
INSERT INTO @Tables (TableName)
SELECT t.TableName
FROM (VALUES (N'stg.ProjectInformation'), (N'dbo.DimProject')) AS t (TableName)
WHERE OBJECT_ID(t.TableName, 'U') IS NOT NULL;

DECLARE @TableName NVARCHAR(128), @Sql NVARCHAR(MAX);

DECLARE table_cursor CURSOR LOCAL FAST_FORWARD FOR SELECT TableName FROM @Tables;
OPEN table_cursor;
FETCH NEXT FROM table_cursor INTO @TableName;
WHILE @@FETCH_STATUS = 0
BEGIN
    SET @Sql = N'
        UPDATE ' + @TableName + N'
        SET SpecLevel = CASE UPPER(LTRIM(RTRIM(CONVERT(NVARCHAR(100), SpecLevel))))
                            WHEN N''LOW'' THEN ''Low''
                            WHEN N''MEDIUM'' THEN ''Medium''
                            WHEN N''HIGH'' THEN ''High''
                        END,
            SiteType = CASE UPPER(LTRIM(RTRIM(CONVERT(NVARCHAR(100), SiteType))))
                           WHEN N''GREENFIELD'' THEN ''Greenfield''
                           WHEN N''BROWNFIELD'' THEN ''Brownfield''
                       END,
            ComplexityRating = CASE
                WHEN TRY_CONVERT(DECIMAL(9,4), ComplexityRating) BETWEEN 1 AND 5
                 AND TRY_CONVERT(DECIMAL(9,4), ComplexityRating)
                     = FLOOR(TRY_CONVERT(DECIMAL(9,4), ComplexityRating))
                    THEN CONVERT(NVARCHAR(100), CONVERT(TINYINT, TRY_CONVERT(DECIMAL(9,4), ComplexityRating)))
            END
        WHERE SpecLevel IS NOT NULL OR SiteType IS NOT NULL OR ComplexityRating IS NOT NULL;

        ALTER TABLE ' + @TableName + N' ALTER COLUMN SpecLevel VARCHAR(10) NULL;
        ALTER TABLE ' + @TableName + N' ALTER COLUMN SiteType VARCHAR(20) NULL;
        ALTER TABLE ' + @TableName + N' ALTER COLUMN ComplexityRating TINYINT NULL;
        ALTER TABLE ' + @TableName + N' ALTER COLUMN TotalHeightGroundToRoof DECIMAL(18,4) NULL;
        ALTER TABLE ' + @TableName + N' ALTER COLUMN BasementArea DECIMAL(18,4) NULL;
        ALTER TABLE ' + @TableName + N' ALTER COLUMN BasementHeight DECIMAL(18,4) NULL;';
    EXEC sp_executesql @Sql;

    FETCH NEXT FROM table_cursor INTO @TableName;
END;
CLOSE table_cursor;
DEALLOCATE table_cursor;
GO

IF OBJECT_ID('dbo.DimProject', 'U') IS NOT NULL
BEGIN
    DECLARE @Flags TABLE (ColumnName SYSNAME NOT NULL);
    INSERT INTO @Flags (ColumnName)
    VALUES
        (N'Demolition'),
        (N'NewBuild'),
        (N'Refurbishment'),
        (N'HorizontalExtension'),
        (N'VerticalExtension'),
        (N'Basement'),
        (N'Asbestos'),
        (N'Contamination');

    DECLARE @AddFlags NVARCHAR(MAX);
    SELECT @AddFlags = STRING_AGG(
        CONVERT(NVARCHAR(MAX), N'ALTER TABLE dbo.DimProject ADD ' + QUOTENAME(ColumnName) + N' BIT NULL;'),
        NCHAR(10)
    )
    FROM @Flags
    WHERE COL_LENGTH('dbo.DimProject', ColumnName) IS NULL;

    IF @AddFlags IS NOT NULL
        EXEC sp_executesql @AddFlags;
END;
GO

IF OBJECT_ID('dbo.DimProject', 'U') IS NOT NULL
BEGIN
    IF OBJECT_ID('dbo.CK_DimProject_SpecLevel', 'C') IS NULL
        EXEC (N'ALTER TABLE dbo.DimProject WITH CHECK ADD CONSTRAINT CK_DimProject_SpecLevel
                CHECK (SpecLevel IN (''Low'', ''Medium'', ''High''));');

    IF OBJECT_ID('dbo.CK_DimProject_SiteType', 'C') IS NULL
        EXEC (N'ALTER TABLE dbo.DimProject WITH CHECK ADD CONSTRAINT CK_DimProject_SiteType
                CHECK (SiteType IN (''Greenfield'', ''Brownfield''));');

    IF OBJECT_ID('dbo.CK_DimProject_ComplexityRating', 'C') IS NULL
        EXEC (N'ALTER TABLE dbo.DimProject WITH CHECK ADD CONSTRAINT CK_DimProject_ComplexityRating
                CHECK (ComplexityRating BETWEEN 1 AND 5);');
END;
GO
