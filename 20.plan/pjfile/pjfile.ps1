# ========================================================================
#  -*- coding: Shift_JIS -*-
# ========================================================================

# ----------------------------------------------------------------------
# 1. Valiables
# ----------------------------------------------------------------------
$CMDNAME=$MyInvocation.MyCommand.Name
$CMDDIR=Split-Path $script:myInvocation.MyCommand.path -parent
$PWDDIR=(Convert-Path .)

$excelFile=Join-Path $CMDDIR "excel.xlsx"
$targetFolder=$PWDDIR

# ----------------------------------------------------------------------
# 2. Init
# ----------------------------------------------------------------------
$rc=0

# ----------------------------------------------------------------------
# 3. Functions
# ----------------------------------------------------------------------

# ----------------------------------------------------------------------
# 4. Main
# ----------------------------------------------------------------------
$itemList = Get-ChildItem $targetFolder -Recurse -Exclude .*,*.bak,*.bk 
#$itemList | Sort-Object -Property FullName | For-Format-Table -Property Directory, Name, FullName, LastWriteTime
$no = 1

try{
  $excel = New-Object -ComObject Excel.Application
  $excel.Visible = $false

  $workbook = $excel.Application.Workbooks.Add()
  $sheet = $workbook.Worksheets(1)
  $workbook.Worksheets(1).Range("A1").Value = "Hello Excel !"
  $sheet.Cells.Item($no+1,1) = "No" 
  $sheet.Cells.Item($no+1,2) = "Directory" 
  $sheet.Cells.Item($no+1,3) = "Name" 
  $sheet.Cells.Item($no+1,4) = "FullName" 
  $sheet.Cells.Item($no+1,5) = "LastWriteTime" 

  $itemList | Sort-Object -Property FullName |  ForEach-Object { 
    $sheet.Cells.Item($no+2,1) = $no 
    $sheet.Cells.Item($no+2,2) = $_.Directory
    $sheet.Cells.Item($no+2,3) = $_.Name
    $sheet.Cells.Item($no+2,4) = $_.FullName
    $sheet.Cells.Item($no+2,5) = $_.LastWriteTime
    $no++
  }
  $null = $sheet.Columns.AutoFit()
  $workbook.SaveAs($excelFile)
  $workbook.Close
  $excel.Quit()

} finally {
  do {
    $cnt = [System.Runtime.Interopservices.Marshal]::ReleaseComObject($excel)
  } while ($cnt -gt 0)
  [System.GC]::Collect()
}

# ----------------------------------------------------------------------
# 5. exit
# ----------------------------------------------------------------------
exit $rc 
