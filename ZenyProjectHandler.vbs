Option Explicit

Dim appDirectory
Dim arguments
Dim command
Dim exitCode
Dim fileSystem
Dim index
Dim pythonwPath
Dim shell

Set fileSystem = CreateObject("Scripting.FileSystemObject")
Set shell = CreateObject("WScript.Shell")

appDirectory = fileSystem.GetParentFolderName(WScript.ScriptFullName)
pythonwPath = fileSystem.BuildPath(appDirectory, ".venv\Scripts\pythonw.exe")

If Not fileSystem.FileExists(pythonwPath) Then
    MsgBox _
        "Ambiente virtual nao encontrado." & vbCrLf & vbCrLf & _
        "Execute setup.bat antes de iniciar o aplicativo.", _
        vbCritical, _
        "Zeny Project Handler"
    WScript.Quit 1
End If

shell.CurrentDirectory = appDirectory
command = QuoteArgument(pythonwPath) & " -m zeny_project_handler_client"

Set arguments = WScript.Arguments
For index = 0 To arguments.Count - 1
    command = command & " " & QuoteArgument(arguments(index))
Next

' pythonw.exe nao cria console. O estilo normal preserva a janela Qt do aplicativo.
On Error Resume Next
exitCode = shell.Run(command, 1, True)
If Err.Number <> 0 Then
    MsgBox _
        "Nao foi possivel iniciar o aplicativo." & vbCrLf & vbCrLf & _
        Err.Description, _
        vbCritical, _
        "Zeny Project Handler"
    WScript.Quit 1
End If
On Error GoTo 0

If exitCode <> 0 Then
    MsgBox _
        "O aplicativo foi encerrado com erro (codigo " & exitCode & ")." & vbCrLf & _
        "Consulte os logs em %LOCALAPPDATA%\ZenyProjectHandler.", _
        vbCritical, _
        "Zeny Project Handler"
End If

WScript.Quit exitCode

Function QuoteArgument(value)
    QuoteArgument = Chr(34) & Replace(CStr(value), Chr(34), Chr(34) & Chr(34)) & Chr(34)
End Function
