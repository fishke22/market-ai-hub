' Run a command line fully hidden (SW_HIDE at process creation).
' Needed because -WindowStyle Hidden still flashes a Windows Terminal window.
Set shell = CreateObject("WScript.Shell")
cmd = ""
For i = 0 To WScript.Arguments.Count - 1
  If i > 0 Then cmd = cmd & " "
  cmd = cmd & """" & WScript.Arguments(i) & """"
Next
shell.Run cmd, 0, False
