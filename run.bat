@echo off
if not exist .venv (
  py -m venv .venv
)
call .venv\Scripts\python.exe -m pip install -r requirements.txt
call .venv\Scripts\python.exe app.py
