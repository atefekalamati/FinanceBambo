@echo off
setlocal

rem  The development host, on the one interpreter that can run all of it.
rem
rem  WHY THIS FILE EXISTS
rem
rem  There are several Python environments on a BAMBO development machine and the Windows
rem  `py` launcher's default is the wrong one. `.venv` at the repository root is Python
rem  3.14 and carries the backend packages but none of the OCR ones, so `python -m devhost`
rem  from an ordinary shell starts a host that serves every endpoint and then fails the
rem  first extraction with `ModuleNotFoundError: No module named 'paddleocr'` -- at request
rem  time, not at startup, because `ImageExtractionAdapter` imports its provider lazily.
rem
rem  So this script does not ask PATH, does not read VIRTUAL_ENV, and does not care which
rem  environment is activated. It names the interpreter outright.
rem
rem  WHY NOT JUST INSTALL PADDLEOCR INTO .venv
rem
rem  Because it does not install there. `backend/extraction/requirements.txt` says so in
rem  its own header, and the setup notes record what it cost to find out: the pins target
rem  Linux, on Windows with CPython 3.12 they resolve to no wheels at all, and 3.14 has
rem  fewer still. The environment that works was built once and verified once; this points
rem  at it rather than trying to reproduce it.

rem  Resolved from THIS file's location, so the script works from any working directory
rem  and survives the repository being cloned somewhere else. %~dp0 ends with a backslash.
set "BACKEND=%~dp0..\.."
set "CANONICAL=%BACKEND%\ai-extraction-env\Scripts\python.exe"

rem  ---------------------------------------------------------------- which interpreter
rem  1. FINANCE_PYTHON, when somebody names one explicitly.
rem  2. This checkout's own ai-extraction-env -- the documented location, and the one a
rem     fresh clone will have.
rem
rem  The override is not a convenience. A virtualenv is gigabytes and is deliberately not
rem  committed, so it lives in exactly ONE checkout. This repository is developed across
rem  several git worktrees of the same project, and in every worktree but that one the
rem  path above simply does not exist. Without the override, this script would work in one
rem  directory and refuse in its siblings -- which is the opposite of reproducible.
if defined FINANCE_PYTHON (
    set "PYTHON=%FINANCE_PYTHON%"
) else (
    set "PYTHON=%CANONICAL%"
)

if not exist "%PYTHON%" (
    echo.
    echo   The canonical interpreter is missing:
    echo       %PYTHON%
    echo.
    echo   This is the environment that carries PaddleOCR and Whisper. Without it the
    echo   host starts but every extraction fails.
    echo.
    echo   If the environment lives in another checkout of this repository, name it:
    echo       set FINANCE_PYTHON=E:\path\to\FINANCE\backend\ai-extraction-env\Scripts\python.exe
    echo.
    echo   See backend/docs/DEV_RUNTIME_FA.md.
    echo.
    exit /b 1
)

rem  Said out loud, because a host that silently used a different interpreter from the one
rem  the reader expects is the fault this whole script exists to prevent.
echo   interpreter: %PYTHON%

rem  `cd` into the backend so `-m devhost` finds the package, and `pushd` so the caller's
rem  directory is restored whatever happens.
pushd "%BACKEND%"
"%PYTHON%" -m devhost %*
set "EXITCODE=%ERRORLEVEL%"
popd

endlocal & exit /b %EXITCODE%
