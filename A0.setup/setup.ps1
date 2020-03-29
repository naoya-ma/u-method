# ========================================================================
#  -*- coding: utf-8 -*-
# ========================================================================

# ----------------------------------------------------------------------
# 1. Valiables
# ----------------------------------------------------------------------
$CMDNAME=$MyInvocation.MyCommand.Name
$CMDDIR=Split-Path $script:myInvocation.MyCommand.path -parent
$PWDDIR=(Convert-Path .)
$PCNAME="123456789012345"

# ----------------------------------------------------------------------
# 2. Init
# ----------------------------------------------------------------------

# ----------------------------------------------------------------------
# 3. Functions
# ----------------------------------------------------------------------

# ----------------------------------------------------------------------
# 4. Main
# ----------------------------------------------------------------------
[void] [System.Reflection.Assembly]::LoadWithPartialName("System.Drawing")
[void] [System.Reflection.Assembly]::LoadWithPartialName("System.Windows.Forms")

# Form 
$Form = New-Object System.Windows.Forms.Form
$Form.Size = New-Object System.Drawing.Size(400,200)
$Form.Text = "Host名変更ツール"
$Form.FormBorderStyle = "FixedSingle"

# Label
$Font = New-Object System.Drawing.Font("ＭＳ ゴシック",10)
$Label = New-Object System.Windows.Forms.Label
$Label.Location = New-Object System.Drawing.Point(10,20)
$Label.Size = New-Object System.Drawing.Size(500,60)
$userinfo = [System.Security.Principal.WindowsIdentity]::GetCurrent()
$Label.Text = "現在のホスト名:    " + (Get-WmiObject -Class Win32_ComputerSystem).Name + "`r`n現在のユーザー名:  " + $userinfo.Name + "`r`n`r`nホスト名を入力して[OK]ボタンをクリックください。"
$label.forecolor = "black"
$Label.Font = $Font

# InputBox
$InputBox = New-Object System.Windows.Forms.TextBox
$InputBox.Location = New-Object System.Drawing.Size(10,80)
$InputBox.Size = New-Object System.Drawing.Size(200,20)
$InputBox.Text = $PCNAME

# OK Button
$OKButton = New-Object System.Windows.Forms.Button
$OKButton.Location = New-Object System.Drawing.Point(80,110)
$OKButton.Size = New-Object System.Drawing.Size(75,30)
$OKButton.Text = "OK"
$OKButton.DialogResult = "OK"

# Cancel Button
$CancelButton = New-Object System.Windows.Forms.Button
$CancelButton.Location = New-Object System.Drawing.Point(170,110)
$CancelButton.Size = New-Object System.Drawing.Size(75,30)
$CancelButton.Text = "Cancel"
$CancelButton.DialogResult = "Cancel"

# Form Layout
$Form.Controls.Add($label )
$Form.Controls.Add($InputBox)
$Form.Controls.Add($OKButton)
$Form.Controls.Add($CancelButton)
$Form.Add_Shown({$Form.Activate()})

# ShowDialog
$result = $Form.ShowDialog()
if ($result -eq "OK")
{
  $x = $InputBox.Text.Trim().ToUpper()
  echo "ホスト名を [$x] に変更します"
  rename-Computer -NewName $x
  #Start-Sleep -Seconds 5
  #rename-Computer -NewName $x -Force -Restart
  $rc=0
}
 else {
  $rc=-1
} 

# ----------------------------------------------------------------------
# 5. exit
# ----------------------------------------------------------------------
exit $rc 
