@echo off
rem Token Quotient in Codex on Windows: Codex runs plugin hooks with cmd.exe, and the Python launcher (py) is
rem there more often than python.exe on the PATH. The hook's input stays on stdin for quotient.py.
where /q py && (py -3 "%~dp0..\scripts\quotient.py" %* & exit /b)
python "%~dp0..\scripts\quotient.py" %*
