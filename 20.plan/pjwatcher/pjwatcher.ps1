# ========================================================================
#  -*- coding: Shift_JIS -*-
# ========================================================================

# ----------------------------------------------------------------------
# 1. Valiables
# ----------------------------------------------------------------------
$CMDNAME=$MyInvocation.MyCommand.Name
$CMDDIR=Split-Path $script:myInvocation.MyCommand.path -parent

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

$json = ConvertFrom-Json -InputObject (Get-Content .\pjwatcher.json -Raw)
Write-Host $json.file1

if ( !(Test-Path $json.file1 )) {
  echo "File not Found"
  return
} 

try {
  $file = $json.file1
  $excel = New-Object -ComObject Excel.Application
  $excel.Visible = $false
  $book = $excel.Workbooks.Open($file)
  $sheet = $excel.Worksheets.Item(1) 
  $line = $json.item1_rows
  while ($true) {
    $item1 = $sheet.Cells.Item($line, $json.item1_columns ).Text
    $item2 = $sheet.Cells.Item($line, $json.title1_columns ).Text
    if ($line -gt $sheet.UsedRange.Rows.Count) { 
      break 
    }
    Write-Host "$item1,$item2" 
    $line++
  }
} catch [Exception] {
  $exp = $error[0].ToString()
} finally {
  $excel.Quit()
  do {
    $cnt = [System.Runtime.Interopservices.Marshal]::ReleaseComObject($excel)
  } while ($cnt -gt 0)
  [System.GC]::Collect()
}
