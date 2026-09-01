Set objShell = WScript.CreateObject("WScript.Shell")
strPath = Wscript.ScriptFullName
Set objFSO = CreateObject("Scripting.FileSystemObject")
Set objFile = objFSO.GetFile(strPath)
strFolder = objFSO.GetParentFolderName(objFile) 
objShell.CurrentDirectory = strFolder
objShell.Run Chr(34) & ".venv\Scripts\python.exe" & Chr(34) & " -m marketdata.tray", 0, False
