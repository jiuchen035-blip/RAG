@echo off
echo === Interview RAG Git Backup Tool ===
if "%1"=="init" goto init
if "%1"=="tag" goto tag
if "%1"=="push" goto push
if "%1"=="rollback" goto rollback
echo Usage: git_backup.bat [init^|tag v1.0^|push^|rollback tag]
goto end

:init
git init
git add .
git commit -m "chore: v1.0 baseline commit"
goto end

:tag
git tag %2
echo Tagged %2
goto end

:push
git push origin main --tags
echo Pushed to remote.
goto end

:rollback
git reset --hard %2
echo Rolled back to %2
goto end

:end
