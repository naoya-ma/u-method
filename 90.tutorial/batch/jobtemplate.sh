#!/bin/sh
# ------------------------------------------------------------------------------
# Shell Sampple
# ------------------------------------------------------------------------------

# ---------------------------------
# 1. Environmenet
# ---------------------------------
CMDNAME=`basename $0`
LOCKFILE="/tmp/$CMDNAME.lock"

# ---------------------------------
# 2. Prelude
# ---------------------------------
while getopts ho: OPT
do
  case $OPT in
    "h" ) FLG_H="TRUE" ;;
    "o" ) FLG_O="TRUE" ; VALUE_O="$OPTARG" ;;
  esac
done
shift $(expr $OPTIND - 1)
if [ "$FLG_H" = "TRUE" ]; then
  echo "usage: $CMDNAME"
  echo "option: -h    This help"
  exit 0 
fi

if [ -f $LOCKFILE ] ; then
  echo "`date +"%Y/%m/%d %H:%M:%S.%03N"`:$CMDNAME:ERROR:exist LOCKFILE. FILE=$LOCKFILE"
  exit 1
fi
touch $LOCKFILE
trap "/bin/rm -f $LOCKFILE;exit 1" 1 2 3 6 7 11
echo "`date +"%Y/%m/%d %H:%M:%S.%03N"`:$CMDNAME:INFO:BEGIN"

# ---------------------------------
# 3. Movement
# ---------------------------------
time1=`date "+%s"`
for x in 1 2 3 4 5 6 7 8 9 10
do
  #echo $x
  echo -n "."
  sleep 1
done

# ---------------------------------
# 3. Finale
# ---------------------------------
/bin/rm -f $LOCKFILE
time2=`date "+%s"`
difftime=`expr $time2 - $time1`
elaps=`echo $difftime | awk '{
  h=$1 / 3600;
  m=($1 - (h / 3600)*3600 )/ 60;
  s=$1 % 60 ;
  printf( "%03dh:%02dm:%02ds", h, m, s );
}'`
echo ""
echo "`date +"%Y/%m/%d %H:%M:%S.%03N"`:$CMDNAME:INFO:END Elaps=$elaps"
exit 0