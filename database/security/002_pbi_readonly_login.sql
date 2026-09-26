/*
  Create (or update) a dedicated read-only SQL login for Power BI.

  Idempotent: safe to run more than once.
  Password is never stored in this file — pass it at run time.

  Grants SELECT on:
    - all dbo.Dim* / dbo.Fact* / dbo.fact* tables
    - dbo.vw_BI_* reporting views (Fact/Dim star views)

  Does not grant staging (stg.*). Use a separate login from AI (ai_readonly).

  Example (PowerShell one-liner):

    sqlcmd -S your_server -d your_database -E -i database/security/002_pbi_readonly_login.sql -v LoginName=pbi_readonly -v Password=REPLACE_ME

  Defaults if LoginName is omitted: pbi_readonly. Password is required.
*/

SET NOCOUNT ON;
GO

DECLARE @LoginName sysname = N'$(LoginName)';
DECLARE @Password  nvarchar(128) = N'$(Password)';

IF @LoginName = N'$(LoginName)' OR @LoginName LIKE N'$(%'
    SET @LoginName = N'pbi_readonly';

IF @Password = N'$(Password)' OR @Password LIKE N'$(%' OR LTRIM(RTRIM(@Password)) = N''
BEGIN
    RAISERROR('Password sqlcmd variable is required. Pass -v Password=...', 16, 1);
    RETURN;
END;

DECLARE @sql nvarchar(max);
DECLARE @obj nvarchar(512);

IF NOT EXISTS (SELECT 1 FROM sys.server_principals WHERE name = @LoginName)
BEGIN
    SET @sql = N'CREATE LOGIN ' + QUOTENAME(@LoginName)
             + N' WITH PASSWORD = ' + QUOTENAME(@Password, '''')
             + N', CHECK_POLICY = ON';
    EXEC sys.sp_executesql @sql;
END;

IF NOT EXISTS (SELECT 1 FROM sys.database_principals WHERE name = @LoginName)
BEGIN
    SET @sql = N'CREATE USER ' + QUOTENAME(@LoginName)
             + N' FOR LOGIN ' + QUOTENAME(@LoginName);
    EXEC sys.sp_executesql @sql;
END;

-- SELECT on warehouse tables
DECLARE grant_tables CURSOR LOCAL FAST_FORWARD FOR
    SELECT QUOTENAME(SCHEMA_NAME(t.schema_id)) + N'.' + QUOTENAME(t.name)
    FROM sys.tables AS t
    WHERE SCHEMA_NAME(t.schema_id) = N'dbo'
      AND (
            t.name LIKE N'Dim%'
         OR t.name LIKE N'Fact%'
         OR t.name LIKE N'fact%'
      );

OPEN grant_tables;
FETCH NEXT FROM grant_tables INTO @obj;
WHILE @@FETCH_STATUS = 0
BEGIN
    SET @sql = N'GRANT SELECT ON OBJECT::' + @obj + N' TO ' + QUOTENAME(@LoginName);
    EXEC sys.sp_executesql @sql;
    FETCH NEXT FROM grant_tables INTO @obj;
END;
CLOSE grant_tables;
DEALLOCATE grant_tables;

-- SELECT on reporting views
DECLARE grant_views CURSOR LOCAL FAST_FORWARD FOR
    SELECT QUOTENAME(SCHEMA_NAME(v.schema_id)) + N'.' + QUOTENAME(v.name)
    FROM sys.views AS v
    WHERE SCHEMA_NAME(v.schema_id) = N'dbo'
      AND v.name LIKE N'vw_BI_%';

OPEN grant_views;
FETCH NEXT FROM grant_views INTO @obj;
WHILE @@FETCH_STATUS = 0
BEGIN
    SET @sql = N'GRANT SELECT ON OBJECT::' + @obj + N' TO ' + QUOTENAME(@LoginName);
    EXEC sys.sp_executesql @sql;
    FETCH NEXT FROM grant_views INTO @obj;
END;
CLOSE grant_views;
DEALLOCATE grant_views;

PRINT N'Power BI read-only login ready: ' + @LoginName
    + N' (SELECT on dbo.Dim* / dbo.Fact* / dbo.vw_BI_*)';
GO
