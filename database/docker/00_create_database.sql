-- Create the integration-test database if it does not exist.
IF DB_ID(N'Benchmarking') IS NULL
BEGIN
    CREATE DATABASE Benchmarking;
END;
GO
