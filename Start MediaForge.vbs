Set fso = CreateObject("Scripting.FileSystemObject")
Set shell = CreateObject("WScript.Shell")
root = fso.GetParentFolderName(WScript.ScriptFullName)
Set processEnv = shell.Environment("Process")
For Each tool In Array("ffmpeg", "ffprobe")
    located = FindTool(fso.BuildPath(root, ".tools\ffmpeg"), tool & ".exe")
    If located <> "" Then processEnv("MEDIAFORGE_" & UCase(tool)) = located
Next
office = fso.BuildPath(root, ".tools\libreoffice\program\soffice.com")
If fso.FileExists(office) Then processEnv("MEDIAFORGE_LIBREOFFICE") = office
binary = fso.BuildPath(root, "dist\MediaForge\MediaForge.exe")
pythonw = fso.BuildPath(root, ".venv\Scripts\pythonw.exe")
shell.CurrentDirectory = root
If fso.FileExists(binary) Then
    shell.Run Chr(34) & binary & Chr(34), 1, False
ElseIf Not fso.FileExists(pythonw) Then
    MsgBox "Please run setup.ps1 first to install MediaForge dependencies.", 48, "MediaForge"
Else
    shell.CurrentDirectory = root
    shell.Run Chr(34) & pythonw & Chr(34) & " -m mediaforge", 0, False
End If

Function FindTool(folderPath, filename)
    FindTool = ""
    If Not fso.FolderExists(folderPath) Then Exit Function
    candidate = fso.BuildPath(folderPath, filename)
    If fso.FileExists(candidate) Then
        FindTool = candidate
        Exit Function
    End If
    For Each subfolder In fso.GetFolder(folderPath).SubFolders
        candidate = FindTool(subfolder.Path, filename)
        If candidate <> "" Then
            FindTool = candidate
            Exit Function
        End If
    Next
End Function
