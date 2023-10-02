CTMOP015 TITLE 'OPC JCL CONVERSION - JOB 3'                             00001027
**********************************************************************  00002027
****       OPC CONVERSION                                               00003027
****       CONTROL-M                                              ****  00004027
****       LICENCED MATERIAL - BMC SOFTWARE INC                         00005027
**********************************************************************  00006027
*  REFORMAT JCL MEMBER TO CTM FORMAT.                                   00007027
*           READ THE JCL MEMBER PASSED BY CTMOP014 AND                  00008027
*           PROCESSES ALL THE OPCBATCH EXEC STEPS.                      00009027
*   RC=0 MEANS THERES NOTHING TO UPDT AND RC=4 OTHERWISE.               00010027
*                                                                    *  00020027
*           THE PROGRAM LOOKS FOR JCL OF THE FOLLOWING KIND:            00030027
*      //STEP   EXEC OPCBATCH                                        *  00040027
*      //SYSIN    DD *                                               *  00050027
*      SRSTAT 'CONTROL-RESOURCE-NAME'  AVAIL(NO)                        00060027
*      OPSTAT ADID(APPLID) WSNAME(WS1) OPNUM(005) STATUS(C)          *  00070027
* OPCBATCH IS CONVERTED TO CTMCDUTL WHICH INVOKES EITHER IOACND FOR     00080027
* SRSTAT CMDS OR CTMAPI (AJF FORCEOK) FOR OPSTAT CMDS)                  00090027
* OTHER CMDS - WSSTAT, BACKUP, JSUACT, OPINFO - ARE IGNORED.            00100027
* MULTI-LINE OPSTAT/SRSTAT CMDS ARE SUPPORTED.                          00110027
* PROGRAM/PROC NAMES WHICH ARE EQUIVALENT TO OPCBATCH                   00111027
*      ARE SPECIFIED IN THE DABATCH FILE.                               00112027
*                                                                       00113027
*  OPC &, % and ? VARIABLES ARE CONVERTED TO CTM AUTO-EDIT %% VARS      00114027
*                                                                       00115027
*  THE FOLLOWING //*%OPC DIRECTIVES are converted:                      00116027
*   SEARCH, FETCH, BEGIN AND END, SCAN, TABLE, RECOVER, SETFORM, SETVAR 00117027
* BASE REGS: R13, R8, R5                                                00118027
* CALLED BY: CTMOP014.                                               *  00119027
*--- CHANGE LOG FOR LEVEL 9404+ -------------------------------------*  00120027
* WC0001 MK 04/27/94 SUPPORT OPC JCL FEATURES-RECOVER,NOERROR,CASECODES 00130027
* BC0083 MK 05/27/94 CORRECT LOGIC FOR CONVERTING COMP= .NE. STMTS      00140027
*--- CHANGE LOG FOR LEVEL 9407+ -------------------------------------*  00150027
* BC0101 MK 12/27/94 ALLOW VARIABLES IN //*%OPC SEARCH TABL NAMES       00160027
* WC0082 MK 12/27/94 SUPPORT TABLE & SCAN DIRECTIVE VIA &AUTSCAN OPTION 00170027
* BC0102 MK 12/27/94 SUPPORT GLOBAL VARIABLE TABL                       00180027
* WC0083 MK 01/01/95 SUPPORT AUTOMATIC CREATN OF AUTO-EDIT VARIABLE LIB 00190027
* BC0103 MK 01/15/95 PREVENT 0C4 WHEN DARESLS FILE EMPTY WITH RESNM>19  00200027
*--- CHANGE LOG FOR LEVEL 9502+ -------------------------------------*  00210027
* WC0090 MK 01/15/95 SIMPLIFY RES-NAME PROCESS >19 VIA &RESNAME OPTION  00220027
* WC0096 MK 02/01/95 SUPPORT OPSTAT STATUS(C) COMMAND VIA CTMCND        00230027
*--- CHANGE LOG FOR LEVEL 9504+ -------------------------------------*  00240027
* BC0118 MK 04/25/95 SUPPORT DATETYP=USA                                00250027
*--- CHANGE LOG FOR LEVEL 9601+ V500 --------------------------------*  00260027
* WC0205 MK 02/25/96 V500 UPGRADE (STAT, @-RESOURCES)                   00270027
*--- CHANGE LOG FOR LEVEL 9605+ -------------------------------------*  00280027
* WC0220 MK 07/02/96 COND-NAME FORMAT JOB/ WITHOUT OPERATION-NO         00290027
* WC0221 MK 07/02/96 ENSURE THAT SPECIAL-RESOURCE-NAME IS UNIQUE        00300027
* WC0225 MK 07/03/96 JCL ENHANCEMENTS FOR OPCBATCH JOBS                 00310027
*--- CHANGE LOG FOR LEVEL 9607+ -------------------------------------*  00320027
* WC0237 MK 08/25/96 CONTINUATION OF WC0001 - SUPPORT FOR RECOVER       00330027
* WC0240 MK 09/27/96 ELIMINATE &COND CONVERSION OPTION.                 00340027
* WC0244 MK 10/15/96 CONTINUATION OF RECOVER PARAMS ON MULTIPLE LINES   00350027
* BC0255 MK 10/16/96 PREVENT 0C4 WHEN OPSTAT HAS INVALID PARAM VALUES   00360027
*--- CHANGE LOG FOR LEVEL 9611+ -------------------------------------*  00370027
* BC0282 MK 12/25/96 JCL MEMBR NOT UPDATED WHEN ONLY JCL VARIABLES      00380027
* BC0283 MK 12/25/96 JCL VARIABLE CONVER - DATA LINE LEN SHOULD BE 79   00390027
* BC0325 MK 03/15/97 A '.' IN JCL VARIABLE IS NOT RECOG AS DELIM        00400027
* BC0326 MK 03/15/97 VARIABLE EXPRESSION &VAR..X&VAR ==> %%VAR.X%%VAR2  00410027
* BC0327 MK 03/16/97 NEW CONVERSION OPTION &RESMAX - MAX RES > 20 CHAR  00420027
* BC0358 MK 06/16/97 WHEN 2 CONSECUTIV &-VAR IN DATALINE, NEXT LINE NG  00430027
* BC0367 MK 08/15/97 LOOK FOR PROC= IN SEARCHING FOR PROCS              00440027
*--- CHANGE LOG FOR LEVEL 9706+ -------------------------------------*  00450027
* BC0395 MK 05/05/98 AE STMT FOR ADDPROC IN RECOVER NOT CORRECT (%%)    00460027
* BC0445 MK 07/07/99 SRSTAT RESOURCE NAME IS CORRUPTED                  00470027
* WC0367 MK 07/07/99 UPGRADE FOR V600 (MCT, IOAENV, ETC.)               00480027
* WC0379 MK 07/07/00 UPGRADE FOR V600 (IOAENV, ETC.)                    00490027
*--- CHANGE LOG FOR V600 --------------------------------------------*  00500027
* BC0515 MK 06/07/01 'JCL' JOBCODE CAUSES CTMOP1501E                    00510027
* WC0405 MK 08/07/01 SUPPORT FOR FLSH STEPCODE                          00520027
* BC0569 MK 11/11/03 GLOBAL,INCLIB/INCMEM BEING ADDED WHEN NOT NEEDED   00530027
* WC0427 MK 11/18/03 SUPPORT RETCODE(HIGHEST|LAST)                      00540027
* WC0428 MK 11/25/03 SUPPRT %%INCLIB DDNAME=EQQ. FETCH, RECOVER/ADDPROC 00550027
*--- CHANGE LOG FOR V620 --------------------------------------------*  00560027
* WC0467 MK 01/27/07 CTMMEM -> IOAMEM; LONG COND FOR RELSUCC            00570027
* BC10024 MK 07/31/07 PGM EQQYRPRC NOT SUPPORTED                        00580027
*                     SUPPRESS %%GLOBAL WHEN &GTABLE IS BLNK            00590027
*                     CONDNAME CONNECTOR CHG TO '-'                     00600027
* BC10025 MK 09/17/07 JCL VARIABLE INCORRECTLY CONVERTD W/ GTABLE=BLNK  00610027
* BC10035 MK 11/17/07 JCL VARIABLE + CONST CONCATENATN &A.X -> %%A%%.X  00620027
* WC10012 MK 02/17/08 OPSTAT STATUS(C) --> CTMAPI FORCE OK              00630027
*                     ELIMINATE &CTMCND OPT; ADDRESSABILITY             00640027
*               SRSTAT AVAIL(KEEP,RESET) - BYPASS THE ADD/DEL COND      00650027
*                     DONT CONVERT '&' BOOLEAN OPER IN JCL IF STMT      00660027
*--- CHANGE LOG FOR V630 --------------------------------------------*  00670027
* WC10018 MK 05/21/08 SUPPORT ADDITIONAL JCL RECOVER CODES              00680027
* WC10026 MK 08/01/08 SUPPORT SETFORM JCL DIRECTIVE (SETVAR NOT SUPP)   00690027
* BC10061 MK 07/07/09 A NON-VARIABLE '1%' IS CONVERTED AS A VAR         00700027
* WC10049 MK 07/12/09 A NON-VARIABLE ,&, IS CONVERTED AS A VAR          00710027
*                     ERROR MSG FOR ?-VARIABLES                         00720027
* BC10064 MK 08/16/09 SETFORM CC IS INCORRECTLY CONVERTED TO %%O$CENT   00730027
*                     CONVERT SETFORM CCYY TO %%$OYEAR                  00740027
*                     CONVERT SETFORM 'VARNAME.' TO '%%CTMVAR..'        00750027
*                     DONT CONVERT VARS DEFINED IN IN-STREAM PROC       00760027
* BC10075 MK 10/16/09 SETFORM: REDUNDANT %%. BEFORE A DELIM CHAR        00770027
*                              INVALID SYSTEM-DATE A-E VAR:$DAY, $MONTH 00780027
* BC10084 MK 11/22/09 OPC TABLE NAME >8 CHARS                           00790027
*                     CLIST CMD %CLIST-NAME TREATED AS AS OPC VAR       00800027
* BC10091 MK 01/31/10 SUPPORT FOR JCLVAR INDEPENDENT VAR/VALUES         00810027
*                     SUPPORT OCLASTXX, OCFRSTXX SETFORM STMTS          00820027
* BC10093 02/06/10 MK ADD OPC TABLENAME TO VAR-DEPEND LIST              00830027
*                     CHECK FOR CLIST/REXX IN SYSPROC (USE IOAMEM)      00840027
* BC10115 05/30/10 MK S0C4 WHEN %ABCDEFGHIJ VAR LEN > 8                 00850027
* BC10119 07/05/10 MK IGNORE SYSTEM SYMBOLIC &SYSUID                    00860027
* WC10076 MS 15/12/10 enable parameters acceptance instead of DEFAULTS  00870027
* WC10075 03/05/11 MK INCREASE &APPLMAX                                 00880027
* WC10083 06/27/11 IL SRSTAT AND OPSTAT CAN START AFTER COL 1           00890027
*                     SKIP OVER BEGIN ACTION KEYWORDS                   00900027
*                     PASSIVE SUPPORT FOR CONTINUED OPSTAT CMD          00910027
* BC10192 09/08/11 IL CONVERT SRSTAT DEV(RESET) Q(n) TO RESET QUANTITY  00920027
* BC10217 01/03/12 IL %%INCMEM=CNVOPCIN instead of SYSTEM               00930027
* BC10268 11/07/12 IL Max of symbols not large enough                   00940027
*                     OPC COMP with 3 items in one row                  00950027
*                     Need support for ACTION=NOSCAN BEGIN and END      00960027
*                     Need support for SETVAR with OCDATE calculation   00970027
*                     Support //*%OPC SETFORM and SETVAR for 3 types    00980027
*                         of dates: OCDATE, OCFRSTC, OCLASTW            00990027
*                     Do not replace & with %% for JCL variables        01000027
*                         defined in //   SET var=    in the JCL        01010027
* BC10273 01/14/13 IL Multi-line SRSTAT support                         01020027
* BC10275 02/21/13 MK DUPLICATE JOBNAMES IN XRF FILE                    01030027
* BC10276 03/01/13 MK UNDO BC10275                                      01040027
*                  MK TERMINATE PROCESSING IF OP018 RETURNS WITH NON-0  01050027
*                  IL USE VARIABLE TABL SHORTENED NAMES LIST FROM 018   01060027
*                  IL BUILD %OPC SETVAR OCDATE=(OCDATE+0CD) FOR SETFORM 01070027
* BC10278 04/08/13 IL Add LIBSYM MEMSYM based on APPL & RBC             01080027
* BC10283 04/30/13 MK AFTER BC10278, WRONG OPERATOR FOR 'IF' STMT (EQ)  01090027
* BC10289 05/16/13 IL LINES LEFT FROM PREVOIUS MEMBR AT THE END         01100027
*                     WTO OF DEBUG LINES REMOVED                        01110027
* BC10294 05/26/13 IL Data shiftd instead of using blanks when &->%%    01120027
*                     ISSUE A MESSAGE IF SHIFT CAUSE LOSS OF DATA       01130027
*                     2 garbage lines at the end if %%IF was added      01140027
* BC10293 06/03/13 MK JOBCODE=* --> S***,U****                          01150027
* BC10297 06/20/13 MK SUPPORT OPERATORS GT, GE, LT, LE IN COMP= STMT    01160027
* BC10312 11/25/13 IL Support dd.mm in SETFORM                          01170027
* BC10314 11/26/13 IL Support SHIFTEND TO control shift for spaces      01180027
* BC10315 12/08/13 IL Support SETVAR OMM OYY                            01190027
*                     Support SHIFTEND for concatenated OPC variables   01200027
* BC10320 01/21/14 IL Support SETVAR CYYYY CYY CMM CYYYYMM ....         01210027
* BC10327 03/19/14 IL Use CAL.NAMES value of APPL CALENDAR for CALENDAR 01220027
* BC10338 11/24/14 IR Multiple conditionions under EXCLUDE              01230027
*                     processed as OR instead of AND                    01240027
* BC10351 11/05/15 IL Support SETVAR ODD OYMD1 OYMD2 OYMD3 CYYMM CDD    01250027
*                                    CDDMMYY CMMYY OYYMM CYYDDD CHHMM   01260027
*                  MK SUPPORT FOR LONG SEARCH/TABLE NAMES (W/ VARS)     01270027
*                     %A.%B --> %%A.%%B (NO CONCATENATION SYM NECESARY) 01280027
*                     SUPPORT SYNTAX: FETCH MEMBER=(XXXX)               01290027
*                     SUPPORT ?-VARIABLE WHEN IT IS THE FIRST (OR ONLY) 01300027
*                             VARIABLE ON THE LINE (NOT SHIFTED)        01310027
*                     FALSE CTMOP1501 MSGS AFTR SPECIAL JOBCODES        01320027
*               S0C4: //*%OPC SETVAR VARNM=SUBSTR(&XXXX,N,M) (NOT SUPP) 01330027
*               S0C4: //*%OPC SETVAR VARNM=(DATEVAR-&XXX.CD) (NOT SUPP) 01340027
*               S0C4: //*%OPC SETVAR VARNM=('VAR'-....)      (NOT SUPP) 01350027
* BC10354 01/21/16 MK CTMOP1505E - PREVENT OVERFLOW WHILE SHIFTING      01360027
*                  IL Support RELSUC as well                            01370027
*                  MK MULTIPLE RELSUCC VALUES NOT PROCESSED             01380027
*                     ERRSTEP=* --> ANYSTEP                             01390027
*                     %A.,%B --> %%A,%%B (REMOVE DOT FOLLOWED BY DELIM) 01400027
* BC10360 12/27/16 MK S0C4 APPLMAX GETMAIN INCORRECT LENGTH FOR CHGFILE 01410027
*               SYSIN PDS CONTAINING OPC CMDS CORRUPTED AFTER INSERT    01420027
*                     FULL SUPPORT FOR CONTINUED OPSTAT STMTS           01430027
*                     SET TRANSR DFLTS FOR ( ) | , TO XLATE TO { } ! ;  01440027
*         CORRUPTD JCL MEM AFTER SETFORM/SETVAR MULTIPLE CONSEC INSERTS 01450027
* BC10370 06/11/17 MK %%SET %%MYMEMSYM LINE INCLUDES GARBAGE (SIADDIFR) 01460027
*                     SUPPORT OPC SETVAR=(DATE-FORMAT) ADDING PHNY +0CD 01470027
*         OP1505:ON OVFLW SQZ OUT EMBEDDED BLNKS BEFORE VARIABLE OCCURS 01480027
*                     SUPPORT OPC SETVAR=('CONST-VAL&VAR1._&VAR2._01')  01490027
*                     SUPPORT OPC SETVAR=(NUMERIC-VAL) (NOT IN QUOTS)   01500027
*                     SUPPORT OPC SETVAR=SUBSTR(&VAR,N,M)               01510027
*                     RESTRUCTURING FOR ADDRESSABILITY                  01520027
* BC10371 07/11/17 MK SPECIAL CHARS IN COND/RESOURCE NAME ADJUSTMENT    01530027
* BC10433 06/10/18 MK FULL SUPPORT FOR CONTINUED SRSTAT STMTS           01540027
*                     CORRECT SRSTAT LOGIC                              01550027
*                     ADD ID-STAMP TO SYSIN PDS MEMBR TO PREVNT RE-CONV 01560027
*                  CTMOP1501/3: WRONG MEMBR NAME WHEN SYSIN PDS MEMBR   01570027
*                     SUPP ALTJOB PARAM OF RECOVER DIRECTIVE ->RERUNMEM 01580027
* BC10447 04/02/19 MK LOOP WHEN PROCESSING LONG ENTRY IN VAR TABLE      01590027
*                     S0C4 WHEN 'SETVAR XXX=(YYY+N)' W/ NO FUNC AFTR N  01600027
* BC10448 04/03/19 MK BAD BRANCH AFTER BC10320                          01610027
*                     SUPPORT CDDD/ODDD JULIAN DATE VARIABLES           01620027
* BC10450 05/20/19 MK SUPPORT SETVAR VARNM=SUBSTR(&VAR.,N,M)            01621027
*                     DO NOT CHK IF %-VAR IS CLISTNAME ON JCL LINE (//) 01622027
*                     '%'-TYPE VARIABLES NOT CONVERTED DUE TO BUG       01623027
*                          IN DIRALL (MEMBER= IGN). CHG TO GETMEM       01624027
*                     //*%OPC TABLE NAME=(GLOBAL) CAUSES S0C4 OR S13C   01625027
*                     SUPPORT MULTI-LINE '// SET' STMT                  01626027
*         RETAIN CONTINUATION COMMA IN COL 72 OF JCL STMT IN SQZ OPER   01627027
*         REDUCE THE NUMBER OF CTMOP1506E ERRORS (JCL LINE OVERFLOW)    01628027
* BC10456 07/10/19 MK S0C4 WHEN JCL SET STMT VAR VALUE CONTAINS COMMA   01629027
* BC10469 11/11/19 MB TO PREVENT SOC4 WHEN JCL SET STMT VARIABLE NAME   01629127
*                     CONTAINS '&' PREFIX OR '.' ADDED CTMOP1508W MSG.  01629227
* BC10562 04/07/21 MK SUPPORT WSSTAT COMMAND TO TAKE WS ONLINE/OFFLINE  01629327
*                     VIA IOACND: CHANGE RESOURCE SBWP_SERVER 99/0      01629427
* BC10693 01/21/22 MK CHG LIBSYM/MEMSYM TO INCLIB/INCMEM FOR JCLVAR TBL 01629527
* BC10758 07/17/22 MK MULTI-LINE SET STMT CORRUPTS LINE COUNTER/POINTER 01629627
*                     DUPLICATE ADDPROCS CAUSE REDUNDANT ERR MSGS       01629727
*                     A FALSE RECOVER LINE CONTIUATION CAUSES ERR MSGS  01629827
*                     FLAGR RESET WHEN ERROR CONDITION ENCOUNTERED      01629927
*                A 'SET' VARIABLE>8 CHARS CAUSES FALSE 'TOO LONG' MSGS  01630027
*                     BEGIN ACTION=SCAN SUPPORT                         01630127
*                  BM TRIPLE-QUOTED VALUE IN A 'SET' STMT VARIABLE      01630264
* BC10893 07/05/23 JM REFORMAT THE ERROR/WARNING MESSAGES               01630329
* BC10894 07/06/23 JM COMPONENTS OF MSGID-CTMOP015-07W ARE NOT CORRECT. 01630429
* BC10904 08/02/23 BM CTMOP014 (THE CALLING PGM) IA RUNNING IN AMODE 31 01630530
* BC10918 08/28/23 NB Jumpify/BASE GPR constraint relief                01630664
*                     GPRs Rx R6 are now freed up                       01630771
*                     BEGIN and BRTRN replaced with SUBRSET and SUBRRET 01630864
*                     as we required subroutine support with a savearea 01630964
*                     but no base addressability/using                  01631064
*                     I.E. new SA to preserve GPRs but NO seperate      01631164
*                     CSECT. Also use of RELAJUMP to explicitly show    01631264
*                     replacement of L/LY LA/LAY ST/STY etc rather than 01631364
*                     using OPSYN only.                                 01631464
**********************************************************************  01631564
*WC10076 PRINT NOGEN                                                    01631664
*--------------------------------------------------------------------   01655792
*WC10076 COPY  DEFAULTS                                                 01655892
         COPY  CTMOPDSC                                        WC10012  01655992
MCT      DSECT *                                              WC0367    01656092
         COPY  CTMMCT                                         WC0205    01656192
         IEABRCX DEFINE                 |Branch long            BC10918 01656292
         MACRO                                                          01656399
&NAME    SUBXSET                                                        01656499
         GBLC  &SUBRNAM                                                 01656599
         GBLC  &SUBRNSA                                                 01656699
&SUBRNAM SETC  '&NAME'                                                  01656799
&SUBRNSA SETC  '&NAME.SA'                                               01656899
&SUBRNSA DS    15F                     |preserve GPRs across SUBRout    01656999
&SUBRNAM DS    0H                                                       01657099
         STMY  14,12,&SUBRNSA          |Save callers GPRs               01657199
         MEND                                                           01657299
         MACRO                                                          01657399
&NAME    SUBXRET &RC                                                    01657499
         GBLC  &SUBRNAM                                                 01657599
         GBLC  &SUBRNSA                                                 01657699
&NAME    DS    0F                                                       01657799
         AIF   ('&RC' NE '0').RC15                                      01657899
         XR    R15,R15                                                  01657999
.RC15    ANOP                                                           01658099
         LY    R14,&SUBRNSA            |Restore callers GPRs            01658199
         LMY   R0,R12,&SUBRNSA+8       |Restore callers GPRs            01658299
         BR    R14                     |Return                          01658399
         MEND                                                           01658499
*&RELEXPL SETB 1                        |Explicit instruction   BC10918 01658592
*         RELAJUMP &RELEXPL             |swap                           01658692
CTMOP015 START                                                          01658892
         BEGIN *,R8,R5,EQUR=YES                                BC10918  01658994
         JLU   MLA#001                 |                       BC10918  01659084
ST       OPSYN  STY                    |                       BC10918  01659184
LA       OPSYN  LAY                    |                       BC10918  01659284
L        OPSYN  LY                     |                       BC10918  01659384
EX       OPSYN  EXRL                   |                       BC10918  01659484
CONSTS   LOCTR ,                                                        01659599
         LTORG                                                          01659699
WSDATA   LOCTR ,                                                        01660084
*BC10904 IOAMODE 31                                          WC10075    01660384
MAINCODE LOCTR ,                       |                       BC10918  01660499
MLA#001  DS    0H                      |                       BC10918  01660584
         USING PARM,R1             ADDRESS PARM                         01660684
* ALSO SET UP PARAMETER LIST FOR CALLING CTMCDPRC                       01660784
         L     R3,PMEMN            POINT TO MEMBR NAME                  01660884
         MVC   MEMBER,0(R3)        KEEP MEMBR                           01660984
         ST    R3,CTM5MEMN         KEEP MEMBR NAME PTR IN PARM BC10064  01661084
         L     R3,PMEMP            POINT TO JCL MEMBR                   01661127
         ST    R3,MEMADDR          KEEP ADDRESS                         01662027
         ST    R3,CTM5MEMP                                      BC10064 01670027
         L     R3,PLINE#           POINT TO JCL LINE COUNT              01680027
         ST    R3,ALINE#           KEEP PTR TO LINE#                    01690027
         MVC   LINE#,0(R3)         KEEP LINE COUNT                      01700027
         ST    R3,CTM5MEML                                      BC10064 01710027
         L     R3,PWORK            POINT TO WORK AREA                   01720027
         ST    R3,AWORK            KEEP PTR                             01730027
         ST    R3,CTM5WRKP                                      BC10064 01740027
         L     R3,PACTMMEM         POINT TO ADDR OF CTMMEM     WC0225   01750027
         MVC   ACTMMEM,0(R3)         KEEP ADDR OF IOAMEM       WC0467   01760027
         MVC   CTM5ACTM,0(R3)      KEEP IN PARM                 BC10064 01770027
&MCTUSE  SETC  'MCT'                                          WC0367    01780027
         L     R3,PMCTADDR         ADDR OF MCT ADDR           WC0367    01790027
         MVC   MCTADDR,0(R3)       MCT ADDR FOR IOAMEM        WC0467    01800027
         L     R3,0(,R3)           MCT ADDR (FOR USING)       WC0367    01810027
         ST    R3,AMCTADDR         SAVE                       WC0367    01820027
         ST    R3,CTM5MCT                                       BC10064 01830027
         L     R3,PDCBERR          ADDR OF DCB FOR ERR FILE   WC0467    01840027
         ST    R3,ERROR            SAVE                       WC0467    01850027
         ST    R3,CTM5ERRF                                      BC10064 01860027
         L     R3,CALNAMEA         R3 -> 8 CHAR DEFAULT CAL NAMEBC10327 01870027
         MVC   CALENDAR,0(R3)      KEEP FOR USAGE               BC10327 01880027
         DROP  R1                                                       01890027
         L     R2,=A(SFVDVADR)     R4 -> DYNAMIC VAR TABL       BC10320 01900027
         LHI   R3,SFVDVASN*SFVDVELN                             BC10320 01910027
         L     R0,=A(SFVDVASK)     R0 -> DYNAMIC VAR TABL  SKL  BC10320 01920027
         LHI   R1,SFVDVASN*SFVDVELN                             BC10320 01930027
         MVCL  R2,R0               FOR EACH JOB RE-INIT THE TAB BC10320 01940027
*  GET AREA FOR APPL-OLD-NAME/APPL-NEW-NAME TABL                WC0096  01950027
         NC    CHGSTART,CHGSTART   DO WE ALREADY HAVE AREA       WC0096 01960027
         BNZ   SKIPBEG             YES                   WC0096 WC0237  01970027
         L     R15,=A(INIT)    DO ALL INITIALIZATON PROCESSES  BC10370  01980027
         BASR  R14,R15                                         BC10370  01990027
         CHI   R15,4                                           BC10370  02010027
         BE    OPCERR                                          BC10370  02020027
         BH    RETURN                                          BC10370  02030027
         L     R1,=A(GLOBAL)                                    BC10327 02040027
         MVI   C'%'(R1),X'00'   TEMP CHANGE TO GLOBL TBL        BC10327 02050027
NOERRGET L     R1,=A(NOERROR)                             WC0001 WC0225 02060027
         L     R3,=A(NOERREC)                                   WC0237  02070027
         GET   (R1),(R3)                                        WC0237  02080027
         MVC   RECVJOBN,=C'********'  SET DEFAULT           WC0001      02090027
         MVC   ERRSTPPR,=C'ANYSTEP '                        WC0001      02100027
         OI    RECVFLAG,DOOK       SET FLAG FOR NOERROR DOOK     WC0001 02110027
         L     R1,=A(GLOBAL)                                    BC10327 02120027
         TRT   0(80,R3),0(R1)      ANY *'S                      BC10327 02140027
         BNZ   OPCERR         YES- NOT SUPPORTED                 WC0001 02150027
         L     R15,=A(PERCENT)                                   WC0001 02160027
         TR    0(80,R3),0(R15)     TRANSLATE % TO * FOR NOERROR  WC0237 02170027
         L     R1,=A(NOERREC)      INIT R1 FOR ONLYCODE          WC0237 02180027
         L     R15,=A(TRTPER)                                  WC10012  02190027
         TRT   0(9,R3),0(R15)     IS THIS JOBNM.STEPN.PROC.CODE WC0237  02200027
         BZ    ONLYCODE            NO - JUST A CODE              WC0001 02210027
         SR    R1,R3     R3=A(NOERREC); GET LENGTH OF JOBNAME    WC0001 02220027
         BCTR  R1,0                                              WC0001 02230027
*BC10918 BM    *+14                NO JOBNAME                    WC0001 02240031
         BM    MLA#100             NO JOBNAME                  BC10918  02241031
         MVC   RECVJOBN,=80C' '          CLEAR              WC0001      02250027
         EX    R1,NOERRMV1                                       WC0001 02260027
MLA#100  DS    0H                                              BC10918  02261031
         LA    R3,2(R1,R3)         POINT PAST FIRST '.'          WC0001 02270027
         TRT   0(9,R3),0(R15)      FIND 2ND '.';  R15 SET ABOVE WC0237  02290027
         BZ    OPCERR                                            WC0001 02300027
         SR    R1,R3                                             WC0001 02310027
         BCTR  R1,0                                              WC0001 02320027
*BC10918 BM    *+14                NO STEPNAME                   WC0001 02330031
         BM    MLA#101             NO STEPNAME                 BC10918  02331031
         MVC   ERRSTPPR,=80C' '                             WC0001      02340027
         EX    R1,NOERRMV2                                       WC0001 02350027
MLA#101  DS    0H                                              BC10918  02351031
         LA    R3,2(R1,R3)         POINT PAST SECND '.'          WC0001 02360027
         TRT   0(9,R3),0(R15)      FIND 3RD  '.'; R15 SET ABOVE WC0237  02362027
         BZ    OPCERR                                            WC0001 02363027
         SR    R1,R3                                             WC0001 02364027
         BCTR  R1,0                                              WC0001 02365027
*BC10918 BM    *+8                 NO PROC STEP NAME             WC0001 02366031
         BM    MLA#102             NO PROC STEP NAME           BC10918  02366131
         EX    R1,NOERRMV3                                       WC0001 02367027
MLA#102  DS    0H                                              BC10918  02367131
         LA    R1,2(R1,R3)         POINT PAST THIRD '.'          WC0001 02368027
ONLYCODE BAL   R9,RTNJOBCO                                       WC0001 02369027
         L     R1,=A(RECVEXT)                                    WC0225 02370027
         PUT   (R1),CTMOPROR                              WC0001 WC0225 02380027
         MVI   RECVFLAG,X'00'       INITIALIZE NEW RECOV REC     WC0001 02390027
         MVC   RECVJOBN,=80C' '                             WC0001      02400027
         MVC   ERRSTPPR(16),=80C' '                             WC0001  02410027
         MVC   JOBCODES(10),=80C' '                         WC0001      02420027
         B     NOERRGET                                          WC0001 02430027
NOERRMV1 MVC   RECVJOBN(*-*),0(R3)                               WC0001 02440027
NOERRMV2 MVC   ERRSTPPR(*-*),0(R3)                               WC0001 02450027
NOERRMV3 MVC   ERRSTPPR+8(*-*),0(R3)                             WC0001 02460027
*                                                                WC0001 02470027
NOERRFIL L     R2,=A(CASECODE)                            WC0001 WC0225 02480027
         L     R3,=A(NOERROR)                             WC0001 WC0225 02490027
         CLOSE ((R3),,(R2))                               WC0001 WC0225 02500027
         L     R1,=A(GLOBAL)                                    BC10327 02510027
         MVI   C'%'(R1),C'%'                                    BC10327 02520027
SKIPBEG  EQU   *                                                 WC0001 02530027
**  GET THE ADDR OF THE VARIABLE TBL LIST (IN CASE OF INSTREAM PROC)    02540027
         LA    R1,CTM5MEMN         POINT TO PARM LIST           BC10064 02550027
         L     R15,CAS51PRC        POINT TO MODULE              BC10064 02560027
         BALR  R14,R15             CALL CTMCDPRC                BC10064 02570027
         ZAP   GOTOCNT1,=P'0'                                           02580027
         ZAP   GOTOCNT2,=P'0'                                           02590027
         ZAP   SRCHCNT,=P'0'                                            02600027
         ZAP   EXP2CNT,=P'0'                                            02610027
         MVC   IFCNT1,=C'00'                                            02620027
         L     R15,=A(DELSTPTB)                                  WC0237 02630027
         MVC   0(80,R15),=80C' '                                 WC0237 02640027
         L     R15,=A(PROCNMTB)                                  WC0237 02650027
         MVC   0(80,R15),=80C' '                                WC0237  02660027
         MVC   DELSTPTR(16),=80C' '                                     02670027
         XC    FLAGS,FLAGS         CLEAR FLAGS BYTE                     02680027
         XC    FLAGS2,FLAGS2         CLEAR FLAGS BYTE                   02690027
         NI    FLAGS0,X'FF'-SCAN     RESET SCAN FLAG             WC0082 02700027
         XC    FLAGSCAN,FLAGSCAN    CLEAR INDICATIONS           BC10315 02710027
         MVC   CALENDAR,=80C' '    INIT TO BLANKS               BC10327 02720027
*BC10351 L     R1,=A(TABLE)          CLEAR FOR NEW JCL MEMBR BC10093    02730027
*BC10351 MVI   0(R1),C' '            CLEAR                    BC10093   02740027
*BC10351 MVC   1(8*L'TABLE-1,R1),0(R1)     L'TABLE=..         BC10093   02750027
         L     R0,=A(TABLE)            CLEAR IT TO BLNKS      BC10351   02760027
         LA    R1,8*L'TABLE                                   BC10351   02770027
         SR    R14,R14                                        BC10351   02780027
         SR    R15,R15                                        BC10351   02790027
MVCLE0   MVCLE R0,R14,C' '(0)                                 BC10351   02800027
         BC    1,MVCLE0            R15 REMAINS 0              BC10351   02810027
         ZAP   SRCHCNT,=P'0'                                  BC10093   02820027
* INIT JCL SET VARIABLES TO BLANKS                              BC10268 02830027
         L     R10,=A(JSTABLE)     R10 -> TABL TO CLEAR        BC10268  02840027
         LHI   R11,JSTABLEL        R11 - LENGTH OF AREA         BC10268 02850027
         XR    R14,R14             R14 - 0 FOR USING FILL CHAR  BC10268 02860027
MVCLE5   MVCLE R10,R14,C' '(0)     R15=0 FROM ABOVE           BC10351   02870027
         BC    1,MVCLE5                                       BC10351   02880027
*  MAIN LOOP - PROCESS OPC STEP                                         02890027
         L     R11,LINE#           GET LINE COUNT                       02900027
         L     R12,MEMADDR         POINT TO FIRST LINE                  02910027
         ST    R12,CHKAMP12        PASS VALUE TO FUNCTION       BC10278 02920027
         ST    R11,CHKAMP11        PASS VALUE TO FUNCTION       BC10278 02930027
         LA    R1,CHKAMPPR                                      BC10278 02940027
         L     R15,=A(SYMINS)                                   BC10278 02950027
         BASR  R14,R15                                          BC10278 02960027
         LTR   R15,R15             ANY ERROR DETECTED ?         BC10278 02970027
*        JNZ   RET                                              BC10278 02980027
         L     R12,CHKAMP12        TAKE UPDATED VALUE FROM FUNC BC10278 02990027
         L     R11,CHKAMP11        TAKE UPDATED VALUE FROM FUNC BC10278 03000027
CHKCARD  EQU   *                                                        03010027
         CLC   =C'//*%OPC ',0(R12)       Q. OPC JCL CARD?               03020027
         BNE   CHKCARD2               NO                                03030027
         BAL   R9,OPCARD              YES                               03040027
         B     NEXTCARD                                                 03050027
CHKCARD2 EQU   *                                                        03060027
*WC10076 AIF   ('&VER' NE 'E').NOTESA2                           WC0001 03070027
         CLI   VER,C'E'                                         WC10076 03080027
         BNE   NOTESA2                                          WC10076 03090027
* CHECK IN ACTION=NOSCAN IN EFFECT                              BC10268 03100027
         TM    FLAGSCAN,$RESOFF    SHOULD WE SKIP RESOLVE?      BC10268 03110027
         BO    NEXTCARD            YES - SKIP TO NEXT CARD      BC10268 03120027
         BAL   R9,CHKAMPRS         CONVERT &, % VARS ON LINE TO %%      03130027
NOTESA2  DS    0H                                               WC10076 03140027
         CLC   =C'//',0(R12)       Q. JCL CARD?                         03150027
         BNE   NEXTCARD            A. NO - SKIP                         03160027
         CLI   2(R12),C'*'         Q. COMMENT CARD?                     03170027
         BE    NEXTCARD            A. YES - SKIP                        03180027
         LHI   R1,0                R1 - 0 TO SIGN ADDING ENTRIESBC10268 03190027
         L     R2,ERROR      LOAD THE ERROR MESSAGE DCB ADDRESS BC10893 03191028
         L     R15,=A(CHKJSET)                                  BC10268 03200027
         BASR  R14,R15                                          BC10268 03210027
         LTR   R15,R15             Q. IS IT JCL SET CARD?       BC10268 03220027
         JZ    NEXTCARD            A. YES - GO TO NEXT          BC10268 03230027
         CHI   R15,16              NO ROOM FOR A VAR ?          BC10268 03240027
         JNE   JSHASROM            NO - CONT                    BC10268 03250027
         BAL   R9,OPCERR           ERR                          BC10268 03270027
         J     NEXTCARD            CONTINUE                     BC10268 03280027
JSHASROM DS    0H                                               BC10268 03290027
         BAL   R10,CHKEXEC         CHECK IF CARD IS EXEC                03300027
         LTR   R15,R15             Q. IS IT EXEC?                       03310027
         BNZ   NEXTCARD            A. NO - SKIP                         03320027
         L     R1,EXECADDR                             BMBMBM BC10758   03340027
         BAL   R10,CHKUCC          CHECK IF OPC  PROC AND IF SO PROCESS 03360027
*WC10076 AIF   ('&VER' NE 'E').NOTESA3                           WC0001 03370027
         CLI   VER,C'E'                                         WC10076 03380027
         BNE   NOTESA3                                          WC10076 03390027
         BAL   R9,CHKAMPRS         CONVERT &, % VARS ON LINE TO %%      03400027
NOTESA3  DS    0H                                               WC10076 03410027
NEXTCARD LA    R12,80(,R12)        POINT TO NEXT CARD                   03420027
         BCT   R11,CHKCARD         CONTINUE WHILE NOT END OF MEMBR      03430027
         TM    FLAGS2,DELWAIT      CLOSE OFF WITH %%ENDIF?       WC0001 03440027
         BNO   RET                                               WC0001 03450027
         L     R3,LINE#                                          WC0001 03460027
         LA    R3,1(,R3)                                         WC0001 03470027
         ST    R3,LINE#                                          WC0001 03480027
         MVC   0(80,R12),=80C' '                                WC0001  03490027
         MVC   0(L'ENDIF,R12),ENDIF                             WC0001  03500027
*         RC=0 NO UPDATE ; RC=4 UPDATE NEEDED                           03510027
RET      EQU   *                                                 WC0225 03520027
         TM    FLAGS0,SYSINPDS     ARE WE PROCESSING A SYSIN PDS WC0225 03530027
         BO    SYSINRET            RET TO SYSIN PROCESSING       WC0225 03540027
         SR    R15,R15             INDICATE NO CHANGES IN MEMBR         03550027
         TM    FLAGS,CHANGES       Q. ANY CHANGES TO MEMBR?             03560027
         BZ    RETURN              A. NO - RETURN                       03570027
         L     R3,LINE#            GET LINE COUNT                       03580027
         L     R4,ALINE#           POINT TO REAL LINE COUNT             03590027
         ST    R3,0(,R4)           KEEP NEW LINE COUNT                  03600027
         LA    R15,4               INDICATE NEED UPDATE                 03610027
RETURN   EQU   *                                                        03620027
*BC10904 IOAMODE 24                                             WC10075 03630030
         BRTRN (15)                                                     03640094
*        SUBRRET                                                        03641094
*===========================================================   BC10918  03650099
*        FIND EXEC CARDS. RC=0 EXEC FOUND; RC=8 NOT FOUND               03651099
CHKEXEC  LA    R15,8               DEFAULT RC                           03660027
         L     R14,=A(BLANK)                                    WC10012 03670027
         TRT   2(9,R12),0(R14)                                  WC10012 03680027
         BZ    EXECNF                                                   03690027
*WC0237  LR    R0,R1               SAVE ADDR OF END OF STEPNAME  WC0001 03700027
         ST    R1,ENDSTEPA         SAVE ADDR OF END OF STEPNAME  WC0237 03710027
         L     R14,=A(NONBLANK)                                 BC10758 03720027
*BC10758 TRT   0(14,R1),NONBLANK                                        03730027
         TRT   0(14,R1),0(R14)                                  BC10758 03740027
         BZ    EXECNF                                                   03750027
         CLC   =C'EXEC ',0(R1)     Q. IS IT EXEC CARD?                  03760027
         BNE   EXECNF              A. NO - NOT FOUND                    03770027
         ST    R1,EXECADDR                              BMBMBM  BC10758 03790327
*WC0237  AIF   ('&VER' NE 'E').NOTESA4                           WC0001 03790527
         TM    FLAGS0,ADDPWAIT     NEED TO ADD INCLIB FOR ADDPROCWC0237 03790627
         BNO   NOADDPR             NO                            WC0237 03790727
         NI    FLAGS0,X'FF'-ADDPWAIT YES                         WC0237 03790827
         L     R2,=A(PROCNMTB)     TBL OF PROCNAMES              WC0237 03790927
         LA    R15,10              AT MOST 10 IN MEMBR          WC0237  03791027
MORINCL  CLI   0(R2),C' '         NO MORE PROCS?                 WC0237 03792027
         BE    NOADDPR            YES                            WC0237 03796027
         BAL   R9,INSERT          ADD %%IF ..., %%INCLIB BLOCK   WC0237 03797027
         LA    R11,1(,R11)        AJUST # LINES                  WC0237 03798027
         BAL   R9,INSERT                                         WC0237 03799027
         LA    R11,1(,R11)        AJUST # LINES                  WC0237 03800027
         BAL   R9,INSERT                                         WC0237 03810031
         MVC   240(80,R12),0(R12)                                WC0237 03820027
         MVC   0(80,R12),=80C' '                                 WC0237 03830027
         MVC   0(11,R12),=C'//* %%IF %%'                  WC0237 BC0395 03840027
         MVC   11(8,R12),0(R2)    ADDPROC NAME            WC0237 BC0395 03850027
         MVC   19(5,R12),=C' EQ 1'                        WC0237 BC0395 03860027
*BC10370 MVC   80(L'INCLIB2,R12),INCLIB2                        WC0237  03870027
         L     R1,=A(INCLIB2)                           WC0237 BC10370  03880027
         MVC   80(L'INCLIB2,R12),0(R1)                         BC10370  03890027
         MVC   80+L'INCLIB2(8,R12),0(R2)                        WC0237  03900027
         MVC   160(L'ENDIF,R12),ENDIF                           WC0237  03910027
         LA    R12,240(,R12)       POINT BACK TO EXEC CARD      WC0237  03920027
         SH    R11,=H'2'          RE-ADJUST R11 BACK            WC0237  03930027
         L     R1,ENDSTEPA        SAVE ADDR OF END OF STEPNAME  WC0237  03940027
         LA    R1,240(,R1)         ADJUST R1                    WC0237  03950027
         ST    R1,ENDSTEPA        SAVE ADDR OF END OF STEPNAME  WC0237  03960027
         LA    R2,8(,R2)          POINT TO NEXT ADDPROC         WC0237  03970027
         BCT   R15,MORINCL                                      WC0237  03980027
NOADDPR  EQU   *                                                 WC0237 03990027
         TM    FLAGS2,DELSTEPF     DOES RECOVER USE DELSTEP      WC0001 04030027
         BNO   EXECFND             NO                            WC0001 04040027
         L     R15,ENDSTEPA        GET  ADDR OF END OF STEPNAME  WC0237 04050027
         LA    R2,3(,R12)          POINT PAST // +1              WC0001 04060027
         SR    R15,R2              LENGTH OF STEPNAME            WC0001 04070027
         MVC   SAVSTPNM,=80C' '    CLEAR                         WC0001 04080027
         EX    R15,MVCSTEP         SAVE THE STEPNAME             WC0001 04090027
         TM    FLAGS2,DELWAIT      IS A DELSTEP WAITING TO END   WC0001 04100027
         BNO   NDELWAIT             NO                           WC0001 04110027
         TM    FLAGS2,DELRNGFL     YES - IS IT A DELSTEP RANGE   WC0001 04120027
         BNO   NDELRNG             NO                            WC0001 04130027
         CLC   SAVSTPNM,DELSTPTR+8 YES- IS IT END OF RANGE?      WC0001 04140027
         BNE   EXECFND             NO - JUST CONTINUE           WC0001  04150027
         NI    FLAGS2,X'FF'-DELRNGFL  YES- RESET RANGE FLAG      WC0001 04160027
         B     EXECFND                                           WC0001 04170027
NDELRNG  NI    FLAGS2,X'FF'-DELWAIT YES- CLOSE OFF WITH %%ENDIF  WC0001 04180027
         BAL   R9,INSERT                                         WC0001 04190027
         MVC   80(80,R12),0(R12)                                 WC0001 04200027
         MVC   0(80,R12),=80C' '                                 WC0001 04210027
         MVC   0(L'ENDIF,R12),ENDIF                             WC0001  04220027
         LA    R12,80(,R12)        POINT BACK TO EXEC CARD       WC0001 04230027
         LA    R1,80(,R1)          ADJUST R1                     WC0001 04240027
NDELWAIT CLC   SAVSTPNM,DELSTPTR   IS THIS FIRST STEP OF A RANGE WC0001 04250027
         BNE   DELNORNG            NO                            WC0001 04260027
         OI    FLAGS2,DELRNGFL     YES                           WC0001 04270027
         B     SETDELAE                                          WC0001 04280027
DELNORNG LA    R15,10              SET UP LOOP TO CHK IF DELSTEP WC0001 04290027
         L     R2,=A(DELSTPTB) TABL WITH DELSTEP NAMES  WC0001  WC0237  04300027
DELSTPLP CLI   0(R2),C' '          END OF TABL                   WC0001 04310027
         BE    EXECFND             YES - NOTHING ELSE TO DO      WC0001 04320027
         CLC   SAVSTPNM,0(R2)      THIS STEPNAME IN TABL?       WC0001  04330027
         BE    SETDELAE            YES -                         WC0001 04340027
         LA    R2,8(,R2)           NEXT ENTRY                    WC0001 04350027
         BCT   R15,DELSTPLP                                      WC0001 04360089
EXECFND  SR    R15,R15             EXEC FOUND R15=0                     04370027
EXECNF   BR    R10                                                      04380027
MVCSTEP  MVC   SAVSTPNM(*-*),2(R12)                              WC0001 04390027
*                                                                WC0001 04400027
SETDELAE EQU   *                                                 WC0001 04410027
         OI    FLAGS2,DELWAIT      SET WAIT FLAG TO CLOSE DELSTEPWC0001 04420027
         BAL   R9,INSERT                                         WC0001 04430027
         MVC   80(80,R12),0(R12)                                 WC0001 04440027
         MVC   0(80,R12),=80C' '                                 WC0001 04450027
         MVC   0(L'IF,R12),IF      //* %%IF                      WC0001 04460027
         MVC   L'IF(2,R12),=C'%%'             %%                 WC0001 04470027
         MVC   L'IF+2(L'SAVSTPNM,R12),SAVSTPNM  SAVSTPNM         WC0001 04480027
         MVC   L'IF+2+L'SAVSTPNM(5,R12),=C' NE 1'         NE 1   WC0001 04490027
         LA    R12,80(,R12)        POINT BACK TO EXEC CARD       WC0001 04500027
         LA    R1,80(,R1)          ADJUST R1                     WC0001 04510027
         B     EXECFND             RETURN                        WC0001 04520027
*        IN EXEC CARD - SEARCH FOR THE OPCESA TRAILER STEP              04530027
CHKUCC   DS    0H                                                       04540027
         LA    R1,4(,R1)           POINT PAST 'EXEC'                    04550027
         L     R14,=A(NONBLANK)                                 BC10758 04560027
*BC10758 TRT   0(15,R1),NONBLANK   FIND FIRST NONBLANK AFTER EXEC       04570027
         TRT   0(15,R1),0(R14)                                  BC10758 04580027
         BZR   R10                 NO - RETURN                          04620027
         CLC   =C'PROC=',0(R1)     IS THERE A PROC=             BC0367  04630027
         BNE   NOPROCEQ            NO                           BC0367  04640027
         LA    R1,5(,R1)           YES - POINT PAST             BC0367  04650027
NOPROCEQ EQU   *                                                BC0367  04660027
         NI    FLAGS0,X'FF'-PGM    RESET FLAG                   WC0225  04670027
         CLC   =C'PGM=',0(R1)      IS IT PGM=                   WC0225  04680027
         BNE   CHKPROC             NO                           WC0225  04690027
         OI    FLAGS0,PGM          YES- SET FLAG                WC0225  04700027
         LA    R1,4(,R1)           POINT PAST PGM=              WC0225  04710027
CHKPROC  EQU   *                                               BC10024  04720027
         CLC   =C'EQQPIFT',0(R1)   UNSUPPORTED PGM (OCL)?      BC10276  04730027
         BE    CHKPROCE            NO -                        BC10276  04740027
         CLC   =C'EQQYRPRC',0(R1)  UNSUPPORTED PGM (OCL)?      BC10024  04750027
         BNE   CHKPROC2            NO -                        BC10024  04760027
CHKPROCE EQU   *                                               BC10276  04770027
         ST    R10,SAVER9          YES- RETURN ADDR            BC10024  04780027
         B     OPCERR              REPORT                      BC10024  04800027
CHKPROC2 EQU   *                                               BC10024  04810027
         L     R3,=A(BATTBL)       GET TABL OF OPCBATCH PROCS  WC0225   04820027
         LA    R15,10              SET UP FOR LOOP (MAX ENTRIES)WC0225  04830027
BTRMLOOP CLI   0(R3),C' '          END OF TABL                  WC0225  04840027
         BER   R10                 YES - NOT AN OPC BATCH STEP  WC0225  04850027
         SR    R2,R2               CLEAR                        WC0225  04860027
         IC    R2,0(R3)            GET LENGTH OF BTRMPROC -1    WC0225  04870027
         STCY  R2,CLCBTRM+1        SET LENGTH OF CLC INSTRUCTN  WC0225  04881046
         LA    R2,1(,R2)           ADD 1 FOR LATER              WC0225  04890027
CLCBTRM  CLC   1(*-*,R3),0(R1)     IS THIS A OPC BATCH PROC     WC0225  04900027
         BE    PROCOK              YES                          WC0225  04910027
         LA    R3,L'BATTBL(,R3)     NO-TRY NEXT ENTRY           WC0225  04920027
         BCT   R15,BTRMLOOP        LOOP                         WC0225  04930027
         BR    R10                 NOT AN OPCBATCH STEP- RETURN WC0225  04940027
PROCOK   NI    FLAGS,X'FF'-ININPUT RESET INPUT FLAG             WC0225  04950027
         MVC   LINE,=80C' '        CLEAR LINE AREA                      04960027
         TM    FLAGS0,PGM          WAS PGM= CODED               WC0225  04970027
         BNO   OPCPGM              NO                           WC0225  04980027
         NI    FLAGS0,X'FF'-PGM    YES - RESET FLAG             WC0225  04990027
         SH    R1,=H'4'            POINT BACK TO PGM            WC0225  05000027
         LA    R2,4(,R2)           ADD 4 TO LENGTH OF 'PROC' NM WC0225  05010027
OPCPGM   EQU   *                                                WC0225  05020027
         LR    R3,R1                   R1=ADDR OF 'OPCBATCH'            05030027
         LA    R1,0(R2,R1)                POINT PAST OPCBATCH  WC0225   05040027
         SR    R3,R12                  LEGTH OF LINE UP TO PGM=OPCB..   05050027
         BCTR  R3,0                    -1                               05060027
MLA#201  DS    0H                                              BC10918  05070146
         MVC   LINE(*-*),0(R12)        MOVE FIRST PART OF LINE          05071046
*BC10918 EX    R3,*-6                                                   05072046
         EX    R3,MLA#201                                               05080046
         LA    R3,LINE+1(R3)                                            05090027
*WC10012 MVC   0(L'CTMCND,R3),CTMCND  REPLACE WITH CTM PROC             05100027
*WC10012 LA    R3,L'CTMCND(,R3)                                         05110027
         MVC   0(7,R3),=C'CTMUTIL'   REPLACE WITH CTMCDUTL    WC10012   05120027
         LA    R3,7(,R3)                                      WC10012   05130027
         LA    R4,70(,R12)                                              05140027
         SR    R4,R1                                                    05150027
MLA#202  DS    0H                                              BC10918  05151046
         MVC   0(*-*,R3),0(R1)                                          05160027
         EX    R4,MLA#202                                               05170046
         MVC   0(71,R12),LINE                                           05180027
         OI    FLAGS,CHANGES                                            05190027
UCCNEXT  LA    R12,80(,R12)        POINT TO NEXT CARD                   05200027
         BCTR  R11,0               DECREMENT LINE COUNT                 05220027
         LTR   R11,R11             Q. ANY MORE?                         05230027
         BP    UCCN3               A. YES - SKIP                        05240027
         LA    R11,1                                                    05250027
         BR    R10                                                      05260027
UCCN3    TM    FLAGS,ININPUT       Q. INPUT PROCESS STARTED?            05270027
         BNO   UCCN2               A. NO - SKIP                         05280027
         CLC   =C'//',0(R12)       Q. END OF INPUT?                     05290027
         BNE   UCCCMND             A. NO - CHECK COMMANDS               05300027
         SH    R12,=H'80'                                               05310027
         LA    R11,1(,R11)                                              05320027
         BR    R10                 RETURN                               05330027
UCCN2    CLC   =C'//*%OPC ',0(R12)       Q. OPC JCL CARD?               05340027
         BNE   UCCN2A                 NO                                05350027
         BAL   R9,OPCARD              YES                               05360027
UCCN2A   CLC   =C'//*',0(R12)     Q. COMMENT? OR SAME //*%OPC? WC0096   05370027
         BE    UCCNEXT             A. YES - SKIP                        05380027
         BAL   R9,CHKAMPRS         CONVERT AMPERSANDS ON LINE TO %%     05390027
         CLC   =C'// ',0(R12)      Q. CONT CARD?                        05400027
         BE    UCCNEXT             A. YES - SKIP                        05410027
** WHAT ABOUT A SYSIN CONCATENATION STMT CONTAINING MORE OPC CMDS??     05420027
         CLC   =C'//SYSIN ',0(R12) Q. SYSIN DD STMT?                    05430027
         BE    CHKDD               A. YES - CHECK IT                    05440027
         CLC   =C'//SYSTSIN ',0(R12) Q. SYSTSIN DD STMT?    WC0225      05450027
         BE    CHKDD               A. YES - CHECK IT        WC0225      05460027
UCCCMND  DS    0H     SUPPORTED CMDS - OPSTAT, SRSTAT, WSSTAT   WC10083 05470027
         L     R14,=A(NONBLANK)                                 BC10758 05480027
*BC10758 TRT   0(71,R12),NONBLANK  R1 -> FIRST NON-BLANK        WC10083 05490027
         TRT   0(71,R12),0(R14)    R1 -> FIRST NON-BLANK BC10758        05491027
*        ST    R1,CMDADDR          SAVE START OF CMD            WC10083 05492027
         CLC   =C'SRSTAT',0(R1)    Q.                           WC10083 05496027
         BE    SRSTAT              A. YES - PROCESS                     05497027
         CLC   =C'OPSTAT',0(R1)    Q.                           WC10083 05498027
         BE    OPSTAT              A. YES - PROCESS         WC0096      05499027
         CLC   =C'WSSTAT',0(R1)    Q.                           BC10562 05500027
         BE    WSSTAT              A. YES - PROCESS             BC10562 05510027
         CLC   =C'/*',0(R12)       Q. END OF INPUT?                     05520027
         BNE   DELINE              NO - DELETE THIS LINE    WC0096      05530027
         BR    R10                          RETURN          WC0096      05570027
DELINE   CLC   =C'//',0(R12)       DELETING JCL LINE             WC0096 05574027
         BE    DELINE2             YES - OK                      WC0096 05575027
         MVC   SAVER9,=A(DELINE2)  NO - UNSUPPORTED COMMAND      WC0096 05576027
         BAL   R9,OPCERR           REPORT                        WC0096 05578027
DELINE2  BAL   R9,DELETE           DELETE LINE                   WC0096 05579027
         B     UCCNEXT             PROCESS NEXT LINE             WC0096 05580027
*        PROCESS //SYSIN (SYSTSIN)                                      05590027
CHKDD    EQU   *                                                        05600027
         L     R14,=A(NONBLANK)                                 BC10758 05610027
*BC10758 TRT   7(10,R12),NONBLANK   FIND FIRST NON BLNK     WC0225      05620027
         TRT   7(10,R12),0(R14)     FIND FIRST NON BLNK  BC10758        05630027
         CLC   =C'DD ',0(R1)       Q. IS IT DD?                         05652027
         BNE   UCCNEXT             A. NO - NEXT CARD                    05653027
*BC10758 TRT   2(10,R1),NONBLANK   FIND FIRST NON BLNK                  05655027
         TRT   2(10,R1),0(R14)     FIND FIRST NON BLNK          BC10758 05656027
         CLI   0(R1),C'*'          Q. IS IT '*'?                        05660027
         BE    UCCNEXT             YES                                  05670027
*WC10076 AIF   ('&PNIBTSD' EQ 'N').NSYSDSN  ONLY IN-STREAM ALLOW WC0225 05680027
         CLI   PNIBTSD,C'N'                                     WC10076 05690027
         BE    NSYSDSN          DONT PROCESS THE SYSIN PDS MEMBRWC10076 05700027
         LA    R15,71(,R12)          GET NUMBER OF BYTES LEFT ON WC0225 05710027
         SR    R15,R1            LINE-SET UP LOOP COUNTER        WC0225 05720027
         NI    FLAGS0,X'FF'-MULTSYSN      RESET FLAG             WC0225 05730027
FINDDSN  CLC   =C'DSN=',0(R1)         NO - LOOK FOR DSN=         WC0225 05740027
         BE    SYSINDSN                    FOUND IT              WC0225 05750027
         CLC   =C'DSNAME=',0(R1)     NO - LOOK FOR DSNAME=       WC0225 05760027
         BE    SYSINDSL                    FOUND IT              WC0225 05770027
         LA    R1,1(,R1)                   KEEP LOOKING          WC0225 05780027
         BCT   R15,FINDDSN                 LOOP                  WC0225 05790027
         TM    FLAGS0,MULTSYSN    ALREADY TESTED 2ND LINE        WC0225 05800027
         BO    SYSINERR         YES - DONT BOTHER LOOKING MORE   WC0225 05810027
         CLC   =C'// ',80(R12)  IS NEXT LINE A CONTINUATION      WC0225 05820027
         BNE   SYSINERR                    NO                    WC0225 05830027
         LA    R1,83(R12)             POINT TO NEXT LINE         WC0225 05840027
         LA    R15,68                 SET COUNTER                WC0225 05850027
         OI    FLAGS0,MULTSYSN       INDICATE MULTI-LINE SYSIN   WC0225 05860027
         B     FINDDSN                                           WC0225 05870027
*WC10076 .NSYSDSN ANOP                                           WC0225 05880027
NSYSDSN  DS    0H                                               WC10076 05890027
SYSINERR NI    FLAGS0,X'FF'-MULTSYSN      RESET FLAG             WC0225 05900027
*BC10893 MVC   WTO2+60(7),=C'SYSIN  '                            WC0225 05910028
         MVC   ERR05CMD(7),=C'SYSIN  '                          BC10893 05911028
         BAL   R9,ERRMSG                                         WC0225 05920027
         BR    R10            A. NO - DIDNT FIND DD * OR DSN=    WC0225 05930027
SYSINDSL LA    R1,3(,R1)          POINT PAST DSNAME=             WC0225 05940027
SYSINDSN LA    R15,4(,R1)          POINT PAST DSN=               WC0225 05950027
         L     R2,=A(TRTPAREN)     FIND OPEN PAREN OR ',' OR ' ' WC0225 05960027
         TRT   0(45,R15),0(R2)                                   WC0225 05970027
         BZ    SYSINERR            NOT A VALID DSN               WC0225 06010027
         SR    R1,R15              LENGTH OF DSN                 WC0225 06020027
         BCTR  R1,0                                              WC0225 06030027
         MVC   DSN,=80C' '                                       WC0225 06040027
         EX    R1,MVCDSN           MVC DSN(*-*),0(R15)           WC0225 06050027
         STM   R14,R1,DSNREGS                                   WC10076 06060027
         L     R1,DSNTRA          TRANSLATION TABL ADDR        WC10076  06070027
DSNFLOOP C     R1,DSNTRE          END OF TABL ?                WC10076  06080027
         BNL   DSNOTFND                                         WC10076 06090027
         CLC   0(44,R1),DSN       DSN EXIST IN TABL?           WC10076  06100027
         BE    DSNFOU             ..yes, translate it           WC10076 06110027
         LA    R1,88(0,R1)                                      WC10076 06120027
         B     DSNFLOOP                                         WC10076 06130027
DSNFOU   DS    0H                                               WC10076 06140027
         MVC   DSN,44(R1)         MOVE DSN IN TABL              WC10076 06150027
DSNOTFND DS    0H                                               WC10076 06160027
         LM    R14,R1,DSNREGS                                   WC10076 06170027
         CLM   R2,1,=C'X'   IS DELIMITER= '(' OR 'X'=',' OR ' ') WC0225 06180027
         BE    SYSINSEQ     'X' MEANS ITS A SEQUENTIAL FILE      WC0225 06190027
         LA    R15,2(R1,R15)       POINT TO MEMBR NAME          WC0225  06200027
         L     R2,=A(TRTPAREN)     FIND CLOSE PAREN              WC0225 06210027
         TRT   0(9,R15),0(R2)                                    WC0225 06220027
         SR    R1,R15                                            WC0225 06224027
         BCTR  R1,0                                              WC0225 06225027
         MVC   SYSINMEM,=80C' '                                  WC0225 06226027
         EX    R1,MVCMEM          MVC   SYSINMEM(*-*),0(R15)     WC0225 06227027
SEQCONT  MVC   GETCNT,=F'100'      SET MAX OF 100 COMMANDS       WC0225 06228027
         L     R2,ASYSIN           ADDR FOR SYSIN MEMBR         WC0225  06229027
         IOAMEM GETMEM,                                        WC0467  *06230027
               IOAMEMA=ACTMMEM,                                WC0467  *06240027
               MCTADDR=MCTADDR,                                WC0467  *06250027
               DSNAME=DSN,                                     WC0467  *06260027
               MEMBER=SYSINMEM,                                WC0467  *06270027
               BUFFADR=(R2),                   MEMER ADDR      WC0467  *06280027
               RECNUM=GETCNT,                                  WC0467  *06290027
               USERID=USERID,                                  WC0467  *06300027
               FROMREC=FROMLINE                                WC0467   06310027
         LTR   R15,R15                                           WC0225 06320027
         BNZ   IOAMEMER                                          WC0467 06330027
         STM   R11,R12,SYSINPRC    SAVE R11,R12                  WC0225 06340027
         MVC   GETCNT,IMRECNUM    SET REAL SYSIN LINE COUNT    WC0467   06350027
         ICM   R11,15,GETCNT       USE NEW MEMBR LINE CNT        WC0225 06360027
         BZ    SYSINEMP            EMPTY MEMBR- NOTHING TO DO    WC0225 06370027
         LR    R12,R2              POINT TO MEMBR               WC0225  06380027
         ZAP   DELCNT,=P'0'        INIT                          WC0225 06390027
         CLC   IDSTAMP,0(R12)      CONVERSION ID-STAMP?         BC10433 06400027
         BE    NOUPDT     SKIP-THIS MEMBR WAS ALREADY PROCESSD BC10433  06410027
         OI    FLAGS0,SYSINPDS                                   WC0225 06420027
* ADD IDENTIFICATION STAMP TO INDICATE THE MEMBR WAS PROCESSED          06430027
         BAL   R9,INSERT        R15 (COUNTER) SAVED ACROSS RTN  BC10433 06440027
         MVC   80(80,R12),0(R12)                                BC10433 06450027
         MVC   0(80,R12),=80C' '                                BC10433 06460027
         MVC   0(L'IDSTAMP,R12),IDSTAMP                         BC10433 06461027
         LA    R12,80(,R12)                                     BC10433 06462027
         B     UCCCMND             PROCESS BATCH TERMINAL CMDS   WC0225 06463027
MVCDSN   MVC   DSN(*-*),0(R15)                                   WC0225 06464027
MVCMEM   MVC   SYSINMEM(*-*),0(R15)                              WC0225 06465027
SYSINRET NI    FLAGS0,X'FF'-SYSINPDS                             WC0225 06466027
         CVB   R1,DELCNT           NUMBER OF RECOREDS DELETED    WC0225 06467027
         LNR   R1,R1               MAKE NEGATIVE                 WC0225 06468027
         A     R1,GETCNT           ADD TO ORIGINAL COUNT         WC0225 06469027
         ST    R1,GETCNT           STORE BACK                    WC0225 06470027
         L     R2,ASYSIN           ADDR FOR SYSIN MEMBR         WC0225  06480027
         IOAMEM PUTMEM,                                         WC0467 *06490027
               IOAMEMA=ACTMMEM,                                 WC0467 *06500027
               MCTADDR=MCTADDR,                                 WC0467 *06510027
               DSNAME=DSN,                                      WC0467 *06520027
               MEMBER=SYSINMEM,                                 WC0467 *06530027
               BUFFADR=(R2),        ADDRESS OF JCL MEMBR        WC0467 *06540027
               RECNUM=GETCNT,                                   WC0467 *06550027
               USERID=USERID,                                   WC0467 *06560027
               FROMREC=FROMLINE,                                WC0467 *06570027
               ACTION=REP,                                      WC0467 *06580027
               ISPFSTAT=Y,                                      WC0467 *06590027
               ESTAE=N,                                         WC0467 *06600027
               DUMP=N                                           WC0467  06610027
         LTR   R15,R15                                           WC0225 06620027
         BNZ   IOAMEMER                                          WC0467 06630027
NOUPDT   EQU   *                                              BC10433   06640027
         IOAMEM FINISH,                                        WC0467  *06650027
               IOAMEMA=ACTMMEM,                                WC0467  *06660027
               MCTADDR=MCTADDR,                                WC0467  *06670027
               DSNAME=DSN,                                     WC0467  *06680027
               MEMBER=SYSINMEM                                 WC0467   06690027
         TM    FLAGS0,SEQFLAG      SEQUENTIAL FILE PROCESSING?   WC0225 06700027
         BO    SEQCOPY2            YES                           WC0225 06710027
SYSINEMP LM    R11,R12,SYSINPRC    RESTORE R11, R12              WC0225 06720027
SYSINEM2 OI    FLAGS,ININPUT TURN ON (IN CASE FILE EMPTY) WC0225        06730027
*  TURN OFF ININPUT AFTER FINISHING SYSIN PDS/SEQ PROCESSING ????       06740027
**SYSINEM2 NI    FLAGS,X'FF'-ININPUT   TURN OFF         WC0225 BC10360  06750027
         B     UCCNEXT                                           WC0225 06760027
IOAMEMER NI    FLAGS0,X'FF'-MULTSYSN      RESET FLAG             WC0467 06770027
         L     R1,ERROR               DCB ADDR FOR MSGS          WC0467 06780027
         ST    R1,IMOUTDCB                                       WC0467 06790027
         CALL  IOAGBE,(IMSTART)       IOAMEM ERROR MSG           WC0467 06800027
         BR    R10                                               WC0467 06810027
*                                                                       06820027
SYSINSEQ RDJFCB (SEQFILE,,SYSINLIB) PLACE SEQFILE DSN IN JFCB    WC0225 06830027
         L     R1,=A(JFCBAREA)   JFCB FOR SEQFILE                WC0225 06840027
         MVC   0(44,R1),DSN      OVERLAY THE DSN - SEQ FILE      WC0225 06850027
         OI    FLAGS0,SEQFLAG SET SEQUENTIAL FILE FLAG           WC0225 06860027
         NI    FLAGS0,X'FF'-SEQEMPTY    RESET EMPTY FLAG         WC0225 06870027
         OPEN  (SEQFILE),TYPE=J                                 WC0225  06880027
         OPEN  (SYSINLIB,(OUTPUT))                              WC0225  06890027
SEQCOPY  GET   SEQFILE           COPY SEQ FILE TO PDS MEMBR    WC0225   06900027
         OI    FLAGS0,SEQEMPTY   SET FLAG- SEQ FILE NOT EMPYT   WC0225  06910027
         LR    R0,R1                                            WC0225  06920027
         PUT   SYSINLIB,(R0)                                    WC0225  06930027
         B     SEQCOPY                                          WC0225  06940027
SEQEOF   CLOSE (SEQFILE,,SYSINLIB)                              WC0225  06950027
         TM    FLAGS0,SEQEMPTY      IS SEQ FILE EMPTY?          WC0225  06960027
         BNO   SYSINEM2             YES - DONT DO ANYTHING      WC0225  06970027
         L     R1,=A(JFCBARE2)                                  WC0225  06980027
         MVC   DSN,0(R1)         OVERLAY THE DSN                WC0225  06990027
         MVC   SYSINMEM,44(R1)    GET THE MEMBR NAME           WC0225   07000027
         B     SEQCONT                                          WC0225  07010027
SEQCOPY2 OPEN  (SEQFILE,(OUTPUT)),TYPE=J                        WC0225  07020027
         OPEN  (SYSINLIB)                                       WC0225  07030027
SEQCOPYL GET   SYSINLIB      COPY BACK PDS MEMBR TO SEQFILE    WC0225   07040027
         LR    R0,R1                                            WC0225  07050027
         PUT   SEQFILE,(R0)                                     WC0225  07060027
         B     SEQCOPYL                                         WC0225  07070027
SYSINEOF NI    FLAGS0,X'FF'-SEQFLAG                             WC0225  07080027
         CLOSE (SEQFILE,,SYSINLIB)                              WC0225  07090027
         B     SYSINEMP                                         WC0225  07100027
*---PROCESS WSSTAT WSNAME(XXXX) STATUS(Y) CMD                           07110027
*    'CHANGE RESOURCE XXXX_SERVER 99'               BC10562             07120027
WSSTAT   OI    FLAGS,ININPUT       INDICATE PROCESSING COMMANDS BC10562 07130027
         MVC   NEWRES,=Cl20'    _SERVER'      WS_SERVER         BC10562 07140027
         MVC   QUANT,=80C' '            CLEAR 0/9999           BC10562  07150027
         LA    R3,80(,R12)              POINT TO END OF LINE    BC10562 07160027
         LA    R7,1(,R1)              POINT PAST WSSTAT         BC10562 07170027
WSPARMS  EQU   *                                                BC10562 07171027
         CLC   =C'WSNAME(',0(R7)     FND WSNAME(XXXX)           BC10562 07171127
         BE    WSNAME                                           BC10562 07171227
         CLC   =C'STATUS(',0(R7)     FND STATUS(X)              BC10562 07171327
         BE    WSSTATUS                                         BC10562 07171427
         B     WSSTLP                                           BC10562 07171527
WSNAME   EQU   *                                                BC10562 07171627
         AHI   R7,7                                             BC10562 07171727
         L     R1,=A(PAREN)          FIND END-PAREN             BC10562 07171827
         TRT   0(5,R7),0(R1)                                    BC10562 07171927
         BZ    DELINE                WS NAME > 4 - ERROR        BC10562 07173227
         SR    R1,R7                 WS NAME LEN                BC10562 07173327
         LA    R15,NEWRES+4         POINT TO '_' OF WS_SERVER   BC10562 07173427
         SR    R15,R1               POINT BACK TO INSERT WS     BC10562 07173527
         BCTR  R1,0                  -1 FOR MOVE                BC10562 07173627
         EX    R1,MVCWSNM                                       BC10562 07173727
         CLI   QUANT,C' '           DO WE HAVE A QUANT?         BC10562 07173827
         BNE   QUANTCMD              YES - WRITE RESCHG         BC10562 07173927
         B     WSPARMS               NO - LOOK FOR IT           BC10562 07174027
MVCWSNM  MVC   0(*-*,R15),0(R7)                                 BC10562 07174127
WSSTATUS EQU   *                                                BC10562 07174227
         AHI   R7,7                                             BC10562 07174327
         MVI   QUANT,C'0'                0 SERVER RES           BC10562 07174427
         CLI   0(R7),C'O'       O= OFFLINE?                     BC10562 07174527
         BE    WSSTAT2                                          BC10562 07174627
         MVC   QUANT(4),=C'9999'      9999 SERVER RES           BC10562 07174727
         CLI   0(R7),C'A'       A= ACTIVE?                      BC10562 07174827
         BNE   DELINE                 UNSUPPRT STATUS           BC10562 07174927
WSSTAT2  CLC   =C'    ',NEWRES       DO WE HAVE A WSNAM?        BC10562 07175027
         BNE   QUANTCMD              YES                        BC10562 07175127
         B     WSPARMS               NO - LOOK FOR IT           BC10562 07175227
WSSTLP   EQU   *                                                BC10562 07175327
         AHI   R7,1                                             BC10562 07175427
         CR    R7,R3                                            BC10562 07175527
         BL    WSPARMS             KEEP LOOPING                 BC10562 07175627
         B     DELINE            ERR - CONTINUATN NOT SUPPRT    BC10562 07175727
*---PROCESS SRSTAT COMMAND-----                                         07175827
SRSTAT   OI    FLAGS,ININPUT       INDICATE PROCESSING COMMANDS         07175927
*BC10433 NI    FLAGS1,X'FF'-$SRSCONT SIGN NO CONT FOUND YET     BC10273 07176027
         OI    FLAGS1,$SRSCONT INDIC WE ARE PROCESSING SRSTAT  BC10433  07177027
         MVC   RESOURCE,=80C' '                                         07178027
         MVC   NEWRES,=80C' '                                           07179027
         MVI   AVAIL,C' '          CLEAR WITH BLANKS          BC10433   07180027
         MVC   QUANT,=80C' '       CLEAR WITH BLANKS          BC10433   07190027
         MVC   DELADD(12),=C'DELETE COND '  SET TO DEFLT VALU BC10433   07200027
*BC10433 SR    R1,R1                                            BC0445  07210027
         L     R15,=A(QUOTAB)                                   WC0225  07220027
         TRT   0(71,R12),0(R15)     FIND START OF RESOURCE      WC0225  07230027
         BZ    DELINE         DIDNT FIND APOSTROPHE/RESNM       WC0096  07270027
         LA    R7,1(,R1)           POINT TO RESOURCE           WC10026  07280027
*BC10433 L     R15,=A(QUOTAB)                                   WC0225  07290027
         TRT   0(45,R7),0(R15)     FIND END OF RESOURCE        WC10026  07300027
         BZ    DELINE              DIDNT FIND END-APOST                 07322027
         LR    R2,R1         SAVE ADDR OF QUOTE AFTER RESNAM   WC0090   07323027
         SR    R1,R7               R1=LENGTH OF RESOURCE-NAME  WC10026  07324027
         LR    R15,R1              SAVE ACTUAL LENGTH IN R15            07325027
         BCTR  R1,0                                                     07326027
         EX    R1,MVCRESS   MVC   RESOURCE(*-*),0(R7)          WC0090   07327027
*    TRANSFORM CHARACTERS IN SPECIAL RESOURCE USING TRANSR VAR  WC10083 07328027
         L     R14,=A(TRTRANS)   TRANSLATE            WC10083 BC10351   07329027
MLA#203  DS    0H                                              BC10918  07329146
         TR    RESOURCE(*-*),0(R14)    TRANSLATE      WC10083 BC10351   07330027
*BC10918 EX    R1,*-6                                           WC10083 07340046
         EX    R1,MLA#203                                       WC10083 07341046
*QSRTRANS DS    0H                                  WC10083 BC10433     07350027
         MVC   NEWRES,RESOURCE                             WC0205       07360027
         CHI   R15,20              MORE THAN 20 CHARS? WC0205  WC0467   07370027
*BC10433 BNH   CONT                     NO                              07380027
         BNH   CONTRES                  NO                     BC10433  07390027
         L     R15,RESTBL                                       WC10076 07400027
RESLOOP  CLI   0(R15),C' '      END OF TBL                       WC0207 07410027
         BE    RESNXST          RESOURCE DOESNT EXIST IN DB     WC0221  07420027
         CLM   R1,1,0(R15)      SAME LENGTH                      WC0221 07430027
         BNE   RESNXT           NO                              WC0221  07440027
MLA#204  DS    0H                                              BC10918  07441046
         CLC   0(*-*,R7),1(R15) MATCHING RES?                   WC10026 07450027
*BC10918 EX    R1,*-6                                           WC0221  07460046
         EX    R1,MLA#204                                       WC0221  07461046
         BNE   RESNXT           NO                              WC0221  07470027
         MVC   NEWRES,45(R15)      YES - USE THE SHORTENED NAME WC0221  07480027
CONTRES  EQU   *                                              BC10433   07490027
         LA    R3,80(,R12)        R3 - POINTS TO END OF SYSIN REC       07500027
         LR    R7,R2   R7- RE-POINT TO RESNAM ENDQUOT/CONTINU BC10433   07510027
CKAVAIL  CLC   =C'AVAIL(',0(R7)     FND AVAIL(XXXXXX)         WC10026   07520027
         BE    AVAILFND                                                 07530027
*BC10433 CLC   =C'DEV(RESET)',0(R7) IS IT QUANTITY RELATED?     BC10192 07540027
*BC10433 JE    DEVQUANT            YES - EXTRAT Q AND CONT.     BC10192 07550027
*BC10433 CLC   =C'DEV(0)',0(R7)     IS IT QUANTITY RELATED?     BC10192 07560027
*BC10433 JE    DEVQUANT            YES - EXTRAT Q AND CONT.     BC10192 07570027
*BC10433 CLC   =C'DEVIATION(RESET)',0(R7) IS IT QNT RELATED?    BC10192 07580027
*BC10433 JE    DEVQUANT            YES - EXTRAT Q AND CONT.     BC10192 07590027
*BC10433 CLC   =C'DEVIATION(0)',0(R7) IS IT QNT RELATED?        BC10192 07600027
*BC10433 JE    DEVQUANT            YES - EXTRAT Q AND CONT.     BC10192 07610027
*BC10433 LA    R9,4                QUANTITY WILL BE AT OFFSET 4 BC10192 07620027
*BC10433 CLC   =C'DEV(',0(R7)       IS IT CHANGE QUANTITY ?     BC10192 07630027
*BC10433 JE    DEVQCNG             YES - EXTRACT VALUE AND CONT BC10192 07640027
*BC10433 LA    R9,10               QUANTITY WILL BE AT OFFSET 10BC10192 07650027
*BC10433 CLC   =C'DEVIATION(',0(R7) IS IT CHANGE QUANTITY ?     BC10192 07660027
*BC10433 JE    DEVQCNG             YES - EXTRACT VALUE AND CONT BC10192 07670027
         L     R2,=A(OPNPAREN)       FIND '(' OF DEV PARAM    BC10433   07680027
         CLC   =C'DEV',0(R7)       'DEVIATION' PARAM?         BC10433   07690027
         BNE   NOTDEV              NO                         BC10433   07700027
CHKQVAL  EQU   *                                              BC10433   07710027
         TRT   1(10,R7),0(R2)      FIND '('                   BC10433   07720027
         BZ    DELINE              NOTFND - NG                BC10433   07760027
         CLI   1(R1),C'R'          RESET?                     BC10433   07770027
         BE    SRSTLP              IGNORE THE DEVIATION/QNT   BC10433   07780027
         CLI   1(R1),C'K'          KEEP?                      BC10433   07790027
         BE    SRSTLP              IGNORE THE DEVIATION/QNT   BC10433   07800027
         B     DEVQCNG             PROCESS THE AMOUNT         BC10433   07810027
NOTDEV   EQU   *                                              BC10433   07820027
         CLC   =C' Q',0(R7)        QUANTITY PARAMETER?        BC10433   07830027
         BE    CHKQVAL             CHECK VALUE OF QNT         BC10433   07840027
SRSTLP   EQU   *                                              BC10433   07841027
         LA    R7,1(,R7)                                      WC10026   07841127
         CR    R7,R3                                          WC10026   07841227
         BL    CKAVAIL             KEEP LOOPING                         07841327
         B     OPSTWRIT            CHECK FOR CONTINU CARD     BC10433   07841427
*BC10433 AHI   R12,80              GO TO NEXT LINE              BC10273 07841527
*BC10433 AHI   R11,-1              DECREMENT LINE COUNT         BC10273 07841627
*BC10433 JNP   SRCONTER            ERROR IF NO ONE LEFT         BC10273 07841727
*BC10433 TM    FLAGS1,$SRSCONT     ARE WE ALREADY IN CONT PROCESBC10273 07841827
*BC10433 JO    SRCONTER            ERROR - CONT OF CONT         BC10273 07841927
*BC10433 OI    FLAGS1,$SRSCONT     SIGN WORKING ON CONT         BC10273 07842027
*BC10433 LA    R3,80(,R12)         R3 -> END OF LINE            BC10273 07843027
*BC10433 LR    R7,R12              R7 - > CONT LINE             BC10273 07844027
*BC10433 J     CKAVAIL             CONTINUE SERACHING           BC10273 07845027
*SRCONTER DS    0H                 ERROR IN CONTINUATION PROCESSBC10273 07846027
*BC10433 AHI   R12,-160            GO TO FIRST CARD             BC10273 07847027
*BC10433 AHI   R11,2               ADJUST COUNT                 BC10273 07848027
*WC10012 B     AVAILNO    - AVAIL NOT FOUND, USE NO (DEFAULT) WC0096    07849027
*BC10192 B     DELINE   - AVAIL NOT FOUND, BYPASS SETTING COND WC10012  07850027
*QUANTNSU DS    0H  NOTIFY CARD FORMAT NOT SUPPORTED   BC10192 BC10433  07860027
* NOTIFY ABOUT THE UNSUPPORTED CONTROL CARD                     BC10192 07870027
*BC10433 MVC   SAVER9,=A(UCCNEXT)       SET RETURN ADDRESS      BC10192 07880027
*BC10433 J     OPCERR       NOTIFY PROBLRM AND THE MEMBR       BC10192  07890027
RESNXT   LA    R15,LRESTBL(,R15)  NXT ENTRY IN SHORT RESNM TBL WC10076  07900027
         B     RESLOOP                                          WC0221  07910027
RESNXST  EQU   *                                                WC0221  07920027
         MVC   NEWRES,0(R7)             USE FIRST 20-BYTES      WC10026 07930027
*BC10893 MVC   WTO1+19(8),MEMBER                                WC0221  07940028
         MVC   ERR02MEM(8),MEMBER       MOVE THE MEMBER NAME    BC10893 07941029
         TM    FLAGS0,SYSINPDS      PROCESSING A SYSIN PDS MEM?BC10433  07950027
*BC10918 BNO   *+10                 NO                         BC10433  07960031
         BNO   MLA#103              NO                         BC10918  07960131
*BC10893 MVC   WTO1+19(8),SYSINMEM  YES                        BC10433  07961028
         MVC   ERR02MEM(8),SYSINMEM YES                        BC10893  07962028
MLA#103  DS    0H                                              BC10918  07963031
*BC10893 MVC   WTO1+36(20),NEWRES                               WC0221  07980028
         MVC   ERR02RES(20),NEWRES  MOVE THE RESNAME           BC10893  07981029
*BC10893 WTO   'CTMOP1503W-XXXXXXXX RESNAME=XXXXXXXXXXXXXXXXXXXX DOES N*07990028
               OT EXIST IN OPC DATABASE'                        BC10273 08000027
         L     R1,ERROR         LOAD THE ADFDRESS OF DCB ERROR BC10893  08001029
         PUT   0(R1),ERROR002       WRITE THE MESSAGE          BC10893  08002029
*BC10433 B     CONT                                             WC0221  08010027
         B     CONTRES                                 WC0221 BC10433   08011027
AVAILFND EQU   *                                                        08012027
         CLI   6(R7),C'K'             AVAIL=KEEP?              WC10026  08013027
*BC10433 BE    DELINE                 DONT SET THE COND CMD    WC10012  08014027
         BE    SRSTLP              DONT SET THE COND WC10012 BC10433    08015027
         CLI   6(R7),C'R'             AVAIL=RESET?             WC10026  08016027
*BC10433 BE    DELINE                 DONT SET THE COND CMD    WC10012  08017027
         BE    SRSTLP              DONT SET THE COND WC10012 BC10433    08018027
         MVC   AVAIL,6(R7)       SAVE AVAIL Y/N VALUE         BC10433   08019027
         CLI   6(R7),C'N'             AVAIL=NO                 WC10026  08020027
         BE    AVAILNO                                                  08030027
         MVC   DELADD(12),=CL12'ADD COND ' ADDCOND FOR AVAIL=YESWC10012 08040027
AVAILNO  DS    0H                                               BC10273 08050027
         B     SRSTLP           SEARCH FOR MORE PARAMS        BC10433   08060027
SRSTATX  EQU   *     FINISH PROCESSING SRSTAT (AFTR CONTINUATNS)BC10433 08070027
*BC10433 MVC   LINE,0(R12)       KEEP ORIGINAL LINE AS COMMENT  BC10273 08080027
*BC10433 MVC   1(71,R12),LINE      FORWARD ONE CHAR             BC10273 08090027
         MVI   0(R12),C'*'       INIT THE LINE AS A COMMENT     BC10273 08100027
*BC10433 BAL   R9,INSERT              ADD AN EXTRA LINE         BC10273 08110027
*BC10433 AHI   R12,80                 ADJUST POINTER            BC10273 08120027
         NI    FLAGS1,X'FF'-$SRSCONT  RESET FOR NXT CMD        BC10433  08130027
         CLI   AVAIL,C' '         DO WE NEED IOACND ADD COND?  BC10433  08140027
         BE    QUANTCMD                   NO                   BC10433  08150027
         MVC   0(72,R12),=80C' '                                BC10273 08160027
         MVC   0(12,R12),DELADD      ADD/DELETE                         08170027
         MVC   12(20,R12),NEWRES     RESNAME (SHORT)                    08180027
         MVC   32(5,R12),=C' STAT'                              WC0205  08190027
*BC10433 MVC   DELADD(12),=C'DELETE COND '  RESET TO DEFLT VALU WC10012 08200027
*BC10433 TM    FLAGS1,$SRSCONT     DO WE HAVE A CONT LINE       BC10273 08210027
*BC10433 JNO   UCCNEXT             YES - MAKE IT A COMMENT      BC10273 08220027
*BC10433 LR    R1,R12              R1 -> CURRENT CARD           BC10273 08230027
*BC10433 AHI   R1,-160             R1 -> BACKWARD 2 CARDS       BC10273 08240027
*BC10433 MVC   LINE,0(R1)          COPY LINE                    BC10273 08250027
*BC10433 MVC   1(71,R1),LINE       PUSH ONE CHAR                BC10273 08260027
*BC10433 MVI   0(R1),C'*'          MAKE IT COMMENT              BC10273 08270027
*BC10433 B     UCCNEXT                                                  08280027
         CLI   QUANT,C' '  DO WE ALSO NEED IOACND CHANGE RESNM? BC10433 08280127
         BE    UCCNEXT               NO                         BC10433 08280227
         BAL   R9,INSERT         YES- ADD AN EXTRA LINE         BC10433 08280327
         AHI   R12,80                 ADJUST POINTER            BC10433 08280427
         B     QUANTCMD               DO 'CHANGE RESOURCE'      BC10433 08280527
MVCRESS  MVC   RESOURCE(*-*),0(R7)    len of resource=44      WC10026   08280627
DEVQCNG  DS    0H      R1 - POINTING TO OPEN PAREN              BC10192 08280827
*BC10433 AR    R7,R9               R7 -> ACTUAL QUANTITY        BC10192 08280927
         LA    R7,1(,R1)           R7 -> ACTUAL QUANTITY        BC10192 08281027
*BC10433 MVC   QUANT,=80C' '       CLEAR WITH BLANKS            BC10192 08282027
         L     R14,=A(PAREN)       LOOK FOR CLOSE PAREN         BC10192 08283027
         TRT   0(6,R7),0(R14)      LOOK FOR CLOSE PAREN         BC10192 08284027
         SR    R1,R7               CALC LENGTH                  BC10192 08288027
*BC10433 AHI   R1,-1                          - Q( AND -1 FOR EXBC10192 08289027
         BCTR  R1,0                - Q( AND -1 FOR EX  BC10433          08290027
         EX    R1,MVCQUANT  COPY QNT TO BUFR:MVC  QUANT(*-*),0(R7)      08300027
*BC10433 CLI   0(R7),C'0'          IS FIRST CHAR A DIGIT?       BC10192 08310027
*BC10433 JL    QUANTCMD      NO -                               BC10192 08320027
*BC10433 MVI   QUANT,C'+'          IF ALL DIGITS - USE +        BC10192 08330027
*BC10433 J     QUANTCMD            NO - JUST CREATE THE COMMAND BC10192 08340027
         B     SRSTLP        LOOP FOR MORE PARAMS              BC10433  08350027
*DEVQUANT DS    0H     LOOK FOR THE QUANTITY PARAM    BC10192  BC10433  08360027
*BC10433 LA    R9,2                OFFSET OF QUANTITY           BC10192 08370027
*BC10433 CLC   =C'Q(',0(R7)        IS IT QUANTITY VALUE         BC10192 08380027
*BC10433 JE    QUANTFND            YES - EXTRAT Q AND CONT.     BC10192 08390027
*BC10433 LA    R9,9                OFFSET OF QUANTITY           BC10192 08400027
*BC10433 CLC   =C'QUANTITY(',0(R7) IS IT QUANTITY VALUE         BC10192 08410027
*BC10433 JE    QUANTFND            YES - EXTRAT Q AND CONT.     BC10192 08420027
*BC10433 LA    R7,1(,R7)                                        BC10192 08430027
*BC10433 CR    R7,R3                                            BC10192 08440027
*BC10433 JL    DEVQUANT                                         BC10192 08450027
*BC10433 J     QUANTNSU             NOTIFY UNSUPPORTED          BC10192 08460027
*QUANTFND DS    0H                                     BC10192 BC10433  08470027
*BC10433 AR    R7,R9               R7 -> ACTUAL QUANTITY        BC10192 08480027
*BC10433 MVC   QUANT,=80C' '       CLEAR WITH BLANKS            BC10192 08490027
*BC10433 L     R14,=A(PAREN)       LOOK FOR CLOSE PAREN         BC10192 08500027
*BC10433 TRT   0(6,R7),0(R14)      LOOK FOR CLOSE PAREN         BC10192 08510027
*BC10433 SR    R1,R7               CALC LENGTH                  BC10192 08520027
*BC10433 AHI   R1,-1                          - Q( AND -1 FOR EXBC10192 08530027
*BC10433 EX    R1,MVCQUANT         COPY QUANTITY TO AN BUFFER   BC10192 08540027
QUANTCMD DS    0H                                               BC10192 08550027
         CLI   QUANT,C' '       DO WE NEED IOACND CHANGE RESNM? BC10433 08560027
         BE    UCCNEXT               NO                         BC10433 08570027
         MVC   0(72,R12),=80C' '                                BC10192 08580027
         MVC   0(15,R12),=C'RESET QUANTITY '  IOACND CHANGE RES BC10192 08590027
         MVC   16(20,R12),NEWRES                                BC10192 08600027
         MVC   47(L'QUANT,R12),QUANT PUT QUANTITY TO CTMUTIL INPBC10192 08610027
*BC10433 TM    FLAGS1,$SRSCONT     DO WE HAVE A CONT LINE       BC10273 08620027
*BC10433 JNO   UCCNEXT             YES - MAKE IT A COMMENT      BC10273 08630027
*BC10433 LR    R1,R12              R1 -> CURRENT CARD           BC10273 08640027
*BC10433 AHI   R1,-80              R1 -> BACKWARD 1 CARDS       BC10273 08650027
*BC10433 MVC   LINE,0(R1)          COPY LINE                    BC10273 08660027
*BC10433 MVC   1(71,R1),LINE       PUSH ONE CHAR                BC10273 08670027
*BC10433 MVI   0(R1),C'*'          MAKE IT COMMENT              BC10273 08680027
         J     UCCNEXT          PROCESS NXT SYSIN CMD           BC10192 08690027
*MVCQUANT MVC   QUANT+1(*-*),0(R7)                  BC10192 BC10433     08700027
MVCQUANT MVC   QUANT(*-*),0(R7)                             BC10433     08710027
*------------------------------------------------------------------     08720027
*        PROCESS OPSTAT COMMAND: STATUS(C) -> CTMAPI FORCEOK            08730027
*- R1 -> 'OPSTAT' ON ENTRY; ->R14 USED AS BASE REG FOR TRT TABL 'PAREN' 08740027
STATUSF  EQU   *                                               BC10360  08750027
         TRT   0(8,R1),0(R14)                            WC0096 WC10012 08760027
         BZ    OPSTOPN             FORMAT ERROR - IGNORE WC0096 BC10360 08800027
*BC10360 CLI   1(R1),C'C'          STATUS=C?                     WC0096 08810027
*BC10360 BNE   DELINE              NO- NOT SUPPORTED             WC0096 08820027
         MVC   STATUS,1(R1)        SAVE THE STATUS              BC10360 08830027
         B     OPSTOPN             YES - LOOK FOR OPERATION NUMB WC0096 08840027
OPSTAT   OI    FLAGS,ININPUT       INDICATE PROCESSING CMDS   WC0096    08850027
         MVC   OPNUM,=80C' '      CLEAR                 WC0240 *BC10360 08860027
         MVC   WSNAM,=80C' '      CLEAR                 WC0096 *BC10360 08870027
         MVC   JOBNAM,=80C' '      CLEAR                WC0096 *BC10360 08880027
         MVC   APPLWORK,=80C' '    CLEAR                WC0096 *BC10360 08890027
         MVI   STATUS,C'C'         INIT IN CASE NOT SPECIFIED   BC10360 08900027
         L     R14,=A(PAREN)       LOOK FOR       PAREN         BC10268 08910027
         LA    R1,6(,R1)           POINT PAST 'OPSTAT'          WC10083 08920027
         ST    R1,OPSTPARM         HOLD FOR NEXT SERACH         WC10083 08930027
OPSTAT2  EQU   *           RESUME HERE IN CONTINUATION, R1 SET BC10360  08940027
         LA    R15,60              SET UP COUNTER                WC0096 08950027
OPSTLP1  CLC   =C' ST',0(R1)       LOOK FOR STATUS PARAMETER     WC0096 08960027
         BE    STATUSF             FOUND STATUS                  WC0096 08970027
         LA    R1,1(,R1)           KEEP LOOKING                  WC0096 08980027
         BCT   R15,OPSTLP1         LOOP                          WC0096 08990027
OPSTOPN  L     R1,OPSTPARM          SEARCH FOR OPER             BC10360 09000027
         LA    R15,60                                            WC0096 09010027
OPSTLP2  CLC   =C' O',0(R1)  OPERATION: LOOK FOR OPNUM PARAMETR  WC0096 09020027
         BE    OPNUMF                                            WC0096 09030027
         LA    R1,1(,R1)                                         WC0096 09040027
         BCT   R15,OPSTLP2                                       WC0096 09050027
         B     OPSTWS         NO OPNUM - SKIP TO LOOK FOR WS    BC10360 09060027
OPNUMF   EQU   *                   LOOK FOR OPEN PAREN   WC0096 WC10012 09070027
         TRT   0(8,R1),0(R14)                            WC0096 WC10012 09080027
         BZ    OPSTWS              FORMAT ERROR - SKIP  WC0096  BC10360 09102027
         MVC   OPNUM,1(R1)  KEEP OPERATN NUM              WC0096 WC0220 09103027
OPSTWS   EQU   *                                                BC10360 09104027
         LA    R15,60                                            WC0096 09105027
         L     R1,OPSTPARM         R1 -> CHAR TO SERACH         WC10083 09106027
OPSTLP3  CLC   =C' W',0(R1)   WORKSTATION: LOOK FOR WSNAME PARM  WC0096 09107027
         BE    WSNAMF                                            WC0096 09108027
         LA    R1,1(,R1)                                         WC0096 09109027
         BCT   R15,OPSTLP3                                       WC0096 09110027
         B     OPSTJOB     NO WSNAME- LOOK FOR JOBNAME   WC0096  WC0240 09120027
WSNAMF   EQU   *                   LOOK FOR OPEN PAREN   WC0096 WC10012 09130027
         TRT   0(8,R1),0(R14)                            WC0096 WC10012 09140027
         BZ    OPSTJOB             FORMAT ERROR - SKIP  WC0096 BC10360  09180027
         LA    R15,1(,R1)          SAVE ADDR OF WS               WC0096 09190027
         TRT   1(5,R1),0(R14)                            WC0096 WC10012 09200027
         BZ    OPSTJOB             WSNAME>4 CHARS        BC0255 BC10360 09240027
         SR    R1,R15              GET LENGTH OF WS              WC0096 09250027
         BCTR  R1,0                                              WC0096 09260027
         EX    R1,MVCWS            MOVE IN WSNAME                WC0096 09270027
OPSTJOB  DS    0H                                               WC10083 09280027
         L     R1,OPSTPARM         R1 -> CHAR TO SERACH         WC10083 09290027
         LA    R15,60                                            WC0096 09300027
OPSTLP4  CLC   =C' J',0(R1)        LOOK FOR JOBNAM PARAMETR      WC0096 09310027
         BE    JOBNAMF                                           WC0096 09320027
         LA    R1,1(,R1)                                         WC0096 09330027
         BCT   R15,OPSTLP4                                       WC0096 09340027
         B     OPSTAPPL                                          WC0096 09350027
JOBNAMF  EQU   *                   LOOK FOR OPEN PAREN  WC0096 WC10012  09360027
         TRT   0(9,R1),0(R14)                           WC0096 WC10012  09370027
         BZ    OPSTAPPL            FORMAT ERROR - SKIP  WC0096 BC10360  09392027
         LA    R15,1(,R1)          SAVE ADDR OF JOBNAM           WC0096 09393027
         TRT   1(9,R1),0(R14)                           WC0096 WC10012  09394027
         BZ    OPSTAPPL           JOBNAME>8 CHARS      BC0255  BC10360  09398027
         SR    R1,R15              GET LENGTH OF JOBNAME         WC0096 09399027
         BCTR  R1,0                                              WC0096 09400027
         EX    R1,MVCJOBN  MVC   JOBNAM(*-*),0(R15) MOVE IN JOBNMWC0096 09410027
         B     OPSTWRIT  WRITE 'AJF FORCEOK MEM=JOBNAME'        WC10012 09420027
OPSTAPPL DS    0H                                               WC10083 09430027
         L     R1,OPSTPARM         R1 -> CHAR TO SERACH         WC10083 09440027
         LA    R15,60                                            WC0096 09450027
OPSTLP5  CLC   =C' A',0(R1)        LOOK FOR APPL ID PARAMETER    WC0096 09460027
         BE    APPLF                                             WC0096 09470027
         LA    R1,1(,R1)                                         WC0096 09480027
         BCT   R15,OPSTLP5                                       WC0096 09490027
         B     OPSTWRIT            CHK FOR CONTIN               BC10360 09500027
APPLF    EQU   *                   LOOK FOR OPEN PAREN   WC0096 WC10012 09510027
         TRT   0(6,R1),0(R14)                            WC0096 WC10012 09520027
         BZ    OPSTWRIT            FORMAT ERROR - SKIP   WC0096 BC10360 09560027
         LA    R15,1(,R1)          SAVE ADDR OF APPL             WC0096 09570027
         TRT   1(17,R1),0(R14)                           WC0096 WC10012 09580027
         SR    R1,R15              GET LENGTH OF APPL            WC0096 09602027
         BCTR  R1,0                                              WC0096 09603027
         EX    R1,MVCAPPL          MOVE IN APPLNAME              WC0096 09604027
OPSTWRIT EQU   *           WRITE CTMAPI AJF FORCEOK             WC10012 09605027
*  CHK FOR CONTINUATN BEFORE CREATING THE 'AJF FORCEOK MEM=XXX'         09606027
*  CHECK IF NEXT CRD STARTS WITH '/' OR WITH ANY OF THE FOLLOW:         09607027
*      BACKUP, OPINFO, OPSTAT, SRSTAT, OR WSSTAT                        09608027
*      OR IF WE ARE AT END OF MEMBR (R11=1)                             09609027
*  IF SO, THEN THERE ARE NO MORE CONTINUATION CARDS,                    09610027
*      AND IF THE STATUS=C                                              09620027
*      WE MUST REPLACE THE CURRENT CARD WITH 'AJF FORCEOK MEM=XXX'      09630027
*  OTHERWISE DELETE CURRENT CRD; SUB 1 FROM R11; POINT TO THE NEXT CARD 09640027
*      AND RETURN TO PROCESS THE CONTINUATION                           09650027
         CHI   R11,1              IS THIS LAST LINE OF MEMB?    BC10360 09660027
         BE    OPSTWRI2           YES - NO CONTIN; WRITE        BC10360 09670027
         CLI   80(R12),C'/'       NXT LINE IS JCL?              BC10360 09680027
         BE    OPSTWRI2           YES - NO CONTIN; WRITE        BC10360 09690027
         TRT   80(70,R12),NONBLANK FIND 1ST NON-BLNK ON NXT CRD BC10360 09700027
         BZ    CONTCRD             ALL BLANK - CONTINUE         BC10360 09740027
         CLC   =C'BACKUP',0(R1)     A NEW CMD?                  BC10360 09750027
         BE    OPSTWRI2             YES - WRITE                 BC10360 09760027
         CLC   =C'OPINFO',0(R1)     A NEW CMD?                  BC10360 09770027
         BE    OPSTWRI2             YES - WRITE                 BC10360 09780027
         CLC   =C'OPSTAT',0(R1)     A NEW CMD?                  BC10360 09790027
         BE    OPSTWRI2             YES - WRITE                 BC10360 09800027
         CLC   =C'SRSTAT',0(R1)     A NEW CMD?                  BC10360 09810027
         BE    OPSTWRI2             YES - WRITE                 BC10360 09820027
         CLC   =C'WSSTAT',0(R1)     A NEW CMD?                  BC10360 09830027
         BNE   CONTCRD              NO - ITS A CONTINUATN       BC10360 09840027
OPSTWRI2 EQU   *                                                BC10360 09850027
         TM    FLAGS1,$SRSCONT              PROCESSING SRSTAT? BC10433  09860027
         BO    SRSTATX                      YES                BC10433  09870027
         CLI   STATUS,C'C'                                      BC10360 09880027
         BNE   DELINE            ONLY STATUS 'C' SUPPORTED      BC10360 09890027
         CLI   JOBNAM,C' '          DO WE HAVE A JOBNAME?       WC10012 09900027
         BE    GETJOBN              NO                          WC10012 09910027
OPSTCONT EQU   *                                      WC10012 BC10360   09920027
***      BAL   R9,INSERT                                      BC10360X  09930027
***      AHI   R12,80                                         BC10360X  09940027
***      BCTR  R11,0                                          BC10360X  09950027
         MVC   0(72,R12),=80C' '                      WC0096  BC10360   09960027
         MVC   0(16,R12),=C'AJF FORCEOK MEM='         WC10012 BC10360   09970027
         MVC   16(8,R12),JOBNAM     YES               WC10012 BC10360   09980027
OPLCN    DS    0H                                               WC10083 09990027
         B     UCCNEXT         OPSTAT CRD PROCESSING ENDED       WC0096 10000027
CONTCRD  EQU   *                                                BC10360 10010027
         MVI   0(R12),C'*'  TURN CURRENT OPSTAT CARD TO COMMENT BC10360 10020027
         LA    R12,80(,R12)           POINT NEXT (CONTIN) CARD  BC10360 10030027
         LR    R1,R12           INIT R1                         BC10360 10040027
         L     R14,=A(NONBLANK)                                 BC10758 10050027
*BC10758 TRT   0(60,R12),NONBLANK    FIND CONTIN TEXT           BC10360 10060027
         TRT   0(60,R12),0(R14)      FIND CONTIN TEXT           BC10758 10070027
*  SHOULD POINT TO THE BLANK BEFORE KEYWORD ON CONTIN CRD               10110027
         BCTR  R1,0        FOR CMPR TO ' A', ' O', ETC.         BC10360 10120027
         ST    R1,OPSTPARM        RESTART POSITION IN CONT LINE BC10360 10130027
         BCTR  R11,0                 ADJ LINE CNT               BC10360 10140027
         LR    R2,R1          IN CASE OF SRSTAT TO RESET R7    BC10433  10150027
         TM    FLAGS1,$SRSCONT              PROCESSING SRSTAT? BC10433  10160027
         BO    CONTRES        RETURN &  RESET R7 AND R3        BC10433  10170027
         B     OPSTAT2  LOOP TO KEEP PROCESSING OPSTAT CONT CRD BC10360 10180027
GETJOBN  EQU   *                FIND JOBNAME IN XRF TBL         WC10012 10190027
         CLI   WSNAM,C' '                       IS THERE WS?    WC10012 10200027
         BE    DELINE                NO - CANT PROCESS          WC10012 10210027
         CLI   OPNUM,C' '            YES. IS THERE OPER?        WC10012 10220027
         BE    DELINE                NO - CANT PROCESS          WC10012 10230027
         BAL   R9,FINDJOB      USE XRF TO FIND JOBNAME          WC10012 10240027
         CLI   JOBNAM,C' '          DO WE HAVE A JOBNAME?       WC10012 10250027
         BNE   OPSTCONT             YES                         WC10012 10260027
         MVC   JOBNAM(4),WSNAM  NO -USE WS_OPER INSTEAD         WC10012 10270027
         L     R15,=A(BLANK)                                    WC10012 10280027
         TRT   JOBNAM(5),0(R15)                                 WC10012 10290027
         MVI   0(R1),C'_'                                       WC10012 10294027
         MVC   1(3,R1),OPNUM                                    WC10012 10295027
         B     OPSTCONT            CONTINUE                     WC10012 10296027
MVCWS    MVC   WSNAM(*-*),0(R15) MOVE IN WSNAME                  WC0096 10297027
MVCJOBN  MVC   JOBNAM(*-*),0(R15) MOVE IN JOBNAM                 WC0096 10298027
MVCAPPL  MVC   APPLWORK(*-*),0(R15) MOVE IN APPLNAME             WC0096 10299027
*                                                                       10300027
FINDJOB  L     R1,JOBSTART                                      WC10012 10310027
         USING JOBDSECT,R1                                      WC10012 10320027
SKIPJ1   EQU   *                                                WC10012 10330027
         CLC   INJOBAPL,APPLWORK      APPL NAME FOUND?          WC10012 10340027
         BNE   SKIPJ2                 IF NO - SKIP.             WC10012 10350027
         CLC   INJOBOP,OPNUM          OPERATION FOUND?          WC10012 10360027
         BNE   SKIPJ2                 IF NO - SKIP.             WC10012 10370027
         CLC   INJOBWS,WSNAM          WS FOUND ?                WC10012 10380027
         BNE   SKIPJ2                 IF NO - SKIP.             WC10012 10390027
*BC10276 CLI   INJOBDUP,C'Y'     IS IT A DUPL JOBNM?      BC10275       10400027
*BC10276 BE    SKIPJX            YES - USE WS#OPER        BC10275       10410027
         MVC   JOBNAM,INJOBNAM        KEEP JOBNAME (OR BLNK)   WC10012  10420027
SKIPJX   EQU   *                                                WC10012 10430027
         BR    R9                                               WC10012 10440027
SKIPJ2   EQU   *                                                WC10012 10450027
         LA    R1,INJOBL(R1)          NEXT ENTRY IN MEMORY      WC10012 10460027
         C     R1,JOBEND              TABL END ?               WC10012  10470027
         BL    SKIPJ1                 IF NO - SKIP              WC10012 10480027
         B     SKIPJX                                           WC10012 10490027
         DROP  R1                                               WC10012 10500027
*    OPCARD RTN    - VARIOUS DIRECTIVES                                 10510027
OPCARD   EQU   *                                                        10520027
         ST    R9,SAVER9                                                10530027
*BC0569  BAL   R14,ADDINCLB                                             10540027
         OI    FLAGS,CHANGES                                            10550027
         LA    R1,7(,R12)          POINT PAST //*%OPC                   10560027
         LA    R15,65                                                   10570027
*OPCLOOP  TM    FLAGS2,RECVMORE RECOVER CONTINUATION PEND WC0001 WC0244 10580027
OPCLOOP  TM    FLAGR,RECVMORE   RECOVER CONTINUATION PENDING     WC0244 10590027
         BO    OPCRECVC                                          WC0001 10600027
         CLC   =C' BEGIN ',0(R1)   IS THIS A 'BEGIN' CARD               10610027
         BE    OPCBEGIN                                                 10620027
         CLC   =C' FETCH ',0(R1)   IS THIS A 'FETCH' CARD               10630027
         BE    OPCFETCH                                                 10640027
         CLC   =C' SEARCH ',0(R1)   IS THIS A 'SEARCH' CARD             10650027
         BE    OPCSRCH                                                  10660027
         CLC   =C'COMP=',0(R1)   IS THIS A 'COMP=' KEYWORD              10670027
         BE    OPCOMP                                                   10680027
         CLC   =C'MEMBER=',0(R1)  IS THIS A MEMBER= KEYWORD FOR FETCH   10690027
         BE    OPCMEMBR                                                 10700027
         CLC   =C' END ',0(R1)    IS THIS A 'END' CARD                  10710027
         BE    OPCEND                                                   10720027
*WC10076 AIF   ('&CTR' NE 'Y').NOCTR                           WC0237   10730027
         CLI   CTR,C'Y'                                         WC10076 10740027
         BNE   NOCTR                                            WC10076 10750027
         CLC   =C' RECOVER ',0(R1)   IS THIS A 'RECOVER' CARD           10760027
         BE    OPCRECV                                         WC0237   10770027
NOCTR    DS    0H                                               WC10076 10780027
         CLC   =C' SCAN ',0(R1)   IS THIS A 'SCAN' CARD                 10790027
         BE    OPCSCAN                                         WC0082   10800027
         CLC   =C' TABLE ',0(R1)                                        10810027
         BE    OPCSRCH                                         WC0082   10820027
         CLC   =C' SETFORM ',0(R1)   IS THIS A 'SETFORM' CARD WC10026   10830027
         BE    OPCSETF                                        WC10026   10840027
         CLC   =C' SETVAR ',0(R1)   IS THIS A 'SETVAR' CARD   WC10026   10850027
         BE    OPSETVAR                                       WC10268   10860027
         LA    R1,1(,R1)                                                10870027
         BCT   R15,OPCLOOP                                              10880027
         TM    FLAGS,FOUND        ACTION=  ALREADY FOUND?               10890027
         BNO   OPCONT             NO - CHECK IF WAITING CONTIN          10900027
         NI    FLAGS,X'FF'-FOUND  YES- RESET                            10910027
         B     OPCFIN             NO MORE PARAMETERS- NEXT CARD         10920027
OPCSCAN  OI    FLAGS0,SCAN    SET SCAN FLAG FOR THIS MEMBR    WC0082    10930027
         B     OPCFIN                                          WC0082   10940027
OPCONT   EQU   *                                                        10950027
         L     R14,=A(NONBLANK)                                 BC10758 10970027
*BC10758 TRT   7(64,R12),NONBLANK  FIND FIRST NON-BLNK AFTER //*%OPC    10980027
         TRT   7(64,R12),0(R14)    FIND 1ST NONBLNK AFTR //*%OPCBC10758 10990027
         BZ    OPCERR                                                   11030027
         TM    FLAGS,EXPCONT      EXPECT A CONTINUATION OF COMP=?       11040027
         BO    OPCONT2            YES                                   11050027
         TM    FLAGS,FETCHCON     EXPECT A CONTINUATION OF FETCH?       11060027
         BO    OPCFIN             YES- COMP= SHOULD FOLLOW              11070027
         TM    FLAGS,SRCHCONF  NO-EXPECT CONTINUATION OF SEARCH ?       11072027
         BNO   OPCERR         NO- UNSUPPORTED OPC STMT                  11073027
         NI    FLAGS,X'FF'-SRCHCONF   RESET FLAG                        11074027
*BC10351 LR    R15,R1               DONE AT FINDSRC0                    11075027
         L     R7,=A(TABLE)       R7 POINTS TO TABL-NAME TABL WC0237    11076027
         B     FINDSRC0                                        BC10093  11077027
OPCONT2  EQU   *                                                        11078027
         NI    FLAGS,X'FF'-EXPCONT    RESET FLAG                        11079027
         B     OPCOMPC            YES                                   11080027
*                                                                       11090027
OPCSETF  EQU   *                  POINT PAST SETFORM            WC10026 11100027
         NI    FLAGS1,X'FF'-$VARPRC   RESET                     BC10064 11110027
         L     R14,=A(NONBLANK)                                 BC10758 11120027
*BC10758 TRT   9(30,R1),NONBLANK  FND 1ST NONBLNK AFTER SETFORM WC10026 11130027
         TRT   9(30,R1),0(R14) FND 1ST NONBLNK AFTER SETFORM    BC10758 11140027
         LR    R3,R1              R3 -> DYNAMIC VARIABLE NAME   BC10268 11180027
         L     R15,=A(EQUAL)    FIND '=' KEYWORD DELIM          BC10268 11190027
         TRT   0(9,R1),0(R15)      FIND '=' ON OPC DIRECTIVE    BC10268 11210027
         JZ    OPCERR              ERR                          BC10268 11232027
         ST    R1,SAVER1            SAVE POS                    BC10268 11233027
         SR    R1,R3               R1 - LEN OF DYNAMIC VAR NAME BC10268 11234027
         MVC   SFVDVAR,=80C' '     CLEAR WITH BLANKS            BC10268 11235027
         AHI   R1,-1               FOR EX                       BC10268 11236027
         EX    R1,SFVDVNMV         KEEP NAME                    BC10268 11237027
         ST    R3,SAVER3            SAVE POS                    BC10276 11238027
         BAL   R9,INSERT    INSERT THE ACCOMOPANIED SETFORM     BC10276 11239027
         AHI   R11,1 ADD 1 TO COUNTER SINCE R12 REMAINS IN PLACEBC10289 11240027
         L     R3,SAVER3            LOAD POS                    BC10276 11250027
         LA    R9,80(,R12)         R9 -> INSERTED LINE          BC10276 11260027
         MVC   0(80,R9),=80C' '    CLEAR WITH BLANKS            BC10268 11270027
         MVC   0(L'SFVDEF1,R9),SFVDEF1       COPY PART 1        BC10276 11280027
         AHI   R9,L'SFVDEF1                                     BC10276 11290027
         EX    R1,SFVDVNR9         TAKE NAME                    BC10276 11300027
         LA    R9,1(R9,R1)         AFTER NAME                   BC10276 11310027
         MVC   0(L'SFVDEF2,R9),SFVDEF2       COPY PART 2        BC10276 11320027
         AHI   R9,L'SFVDEF2                                     BC10276 11330027
         EX    R1,SFVDVNR9         TAKE NAME                    BC10276 11340027
         LA    R9,1(R9,R1)         AFTER NAME                   BC10276 11350027
         MVC   0(L'SFVDEF3,R9),SFVDEF3       COPY PART 3        BC10276 11360027
         AHI   R9,L'SFVDEF3                                     BC10276 11370027
* GET HEAD OF SAVED LIST OF DYNAMIC VARIABLES                   BC10268 11380027
         L     R4,=A(SFVDVADR)     R4 -> DYNAMIC VAR TABL       BC10268 11390027
         USING SFVDV,R4                                         BC10268 11400027
SFVENLP  DS    0H                                               BC10268 11410027
         CLC   SFVDVNAM,SFVDVAR    MATCHED ENTRY FOUND?         BC10268 11420027
         JE    SFVNENTF            YES - REUSE ENTRY            BC10268 11430027
         CLC   SFVDVNAM,=80C' '    END OF ENTRIES?              BC10268 11440027
         JE    SFVNENTF            YES - TAKE FIRST AVAILA      BC10268 11450027
         AHI   R4,SFVDVELN         NO - CONT SEARCH WITH NEXT   BC10268 11460027
         J     SFVENLP             CONT TO LOOP                 BC10268 11470027
SFVNENTF DS    0H                                               BC10268 11480027
         MVC   SFVDVNAM,SFVDVAR    COPY THE VALUE TO LIST       BC10268 11490027
         L     R1,SAVER1           RESTORE POS ON OPC DIRECTIV  BC10268 11500027
         LA    R3,2(,R1)           R3 -> PAST '=(' ON DIRECTIV  BC10268 11510027
         L     R15,=A(PAREN)    FIND ')' - END OF VALUE         BC10268 11520027
         TRT   0(60,R3),0(R15)     FIND '=' ON OPC DIRECTIVE    BC10268 11540027
         JZ    OPCERR              ERR                          BC10268 11580027
         SR    R1,R3               R1 - LEN OF DYNAMIC VAR NAME BC10268 11590027
         AHI   R1,-1               FOR EX (NO ) NEEDED          BC10268 11600027
         MVC   SFVDVVAL,=80C' '    CLEAR AREA                   BC10268 11610027
         EX    R1,SFVDVVMV         KEEP VALUE                   BC10268 11620027
         J     OPCFIN             NO MORE PARAMETERS- NEXT CARD BC10268 11630027
*  DONT USE R9 IN THIS RTN - NEEDED FOR RETURN ON OPCERR        BC10276 11670027
OPSETVAR DS    0H                 R1 -> SETVAR-1                BC10268 11680027
         ST    R1,SAVER1            SAVE POS                    BC10327 11690027
*      FIND APPLICATION OF JOB TO BE PLACED IN APPLWORK         BC10327 11700027
         L     R15,=A(FJOBAPPL)    FIND APPL OF JOB             BC10327 11710027
         BASR  R14,R15             FIND APPL OF JOB             BC10327 11720027
* FIND CALENDAR OF APPLICATION                                  BC10327 11730027
         L     R9,CHGSTART                                      BC10327 11740027
CALSRCHL DS    0H                  SEARCH FOR CALENDAR OF APPL  BC10327 11750027
         CLC   0(16,R9),APPLWORK   FOUND APPL OF THE JOB ?      BC10327 11760027
         JE    CALFND              YES - USE IT                 BC10327 11770027
         AHI   R9,32               R9 -> NEXT APPL              BC10327 11780027
         C     R9,CHGEND           R9 -> OVER LAST?             BC10327 11790027
         JL    CALSRCHL            NOT - CONT LOOP              BC10327 11800027
         MVC   CALENDAR,=CL8'NOCAL' USE DEFAULT VALUE           BC10327 11810027
         J     CALCONT             CONT                         BC10327 11820027
*        PUT IN CALENDAR FIELD                                  BC10327 11830027
CALFND   DS    0H                                               BC10327 11840027
         MVC   CALENDAR,24(R9)     USE CALENDAR PF APPL         BC10327 11850027
CALCONT  DS    0H                                               BC10327 11860027
         L     R1,SAVER1           RESTORE POS ON OPC DIRECTIV  BC10327 11870027
         L     R14,=A(NONBLANK)                                 BC10758 11880027
*BC10758 TRT   8(30,R1),NONBLANK  FND 1ST NONBLNK AFTER SETVAR  BC10268 11890027
         TRT   8(30,R1),0(R14)   FND 1ST NONBLNK AFTER SETVAR  BC10758  11900027
         LR    R3,R1              R3 -> DYNAMIC VARIABLE NAME   BC10268 11922027
         L     R15,=A(EQUAL)    FIND '=' KEYWORD DELIM          BC10268 11923027
         TRT   0(9,R1),0(R15)      FIND '=' ON OPC DIRECTIVE    BC10268 11925027
         JZ    OPCERR              ERR                          BC10268 11929027
         ST    R1,SAVER1            SAVE POS OF '='             BC10268 11930027
         SR    R1,R3               R1 - LEN OF VAR NAME BC10268         11940027
         MVC   SFVUVAR,=80C' '     CLEAR WITH BLANKS            BC10268 11950027
         MVC   SFVUDVN,=80C' '     CLEAR WITH BLANKS            BC10370 11960027
         MVC   SFVNUM,=80C' '      CLEAR WITH BLANKS            BC10370 11970027
         MVC   VARLINE,=80C' '    CLEAR FOR LATER             BC10370   11980027
         AHI   R1,-1               FOR EX                       BC10268 11990027
         EX    R1,SFVUVNMV         KEEP VARIABLE NAME SFVUVAR   BC10268 12000027
         L     R1,SAVER1           RESTORE POS ON OPC DIRECTIV  BC10268 12010027
         CLC   =C'SUBSTR(',1(R1)   SETVAR VARNAME=SUBSTR(XXX...)BC10351 12020027
         BE    DOSUBSTR                                         BC10370 12030027
         LA    R3,2(,R1)           R3 -> PAST '=(' ON DIRECTIV  BC10268 12040027
         CLI   0(R3),C''''        QUOTD VALUE                  BC10370  12050027
         BE    CHKCONST           CHK IF ITS CONSTANT VAL      BC10370  12060027
         L     R15,=A(DELIM)    FIND END OF VALUE               BC10268 12070027
         TRT   0(60,R3),0(R15)     FIND END OF VALUE            BC10268 12090027
         JZ    OPCERR              ERR                          BC10268 12130027
         ST    R1,SAVER1            SAVE POS                    BC10268 12140027
         SR    R1,R3       R1 - LEN OF DYNAM VAR NAME:CYY,ETC.  BC10268 12142027
         BZ    OPCERR    0 LEN NG (MAYBE QUOTED VAL  -SEE ABOV) BC10351 12143027
*BC10370 MVC   SFVUDVN,=80C' '     CLEAR WITH BLANKS            BC10268 12144027
         AHI   R1,-1               FOR EX (NO ) NEEDED          BC10268 12145027
         EX    R1,SFVUVVMV         KEEP DYN VAR NAM             BC10268 12146027
         L     R15,=A(NUMTRT)                                  BC10370  12147027
         EX    R1,TRTUDVN        TRT   SFVUDVN(*-*),0(R15)     BC10370  12148027
         BZ    NUMCONST        CASE: SETVAR XX=(NUMERIC-CONST) BC10370  12170027
         L     R1,SAVER1           RESTORE POS ON END OF VALUE  BC10268 12180027
         L     R15,=A(PLMIN)    FIND '+/-' OR )                 BC10268 12190027
         TRT   0(60,R1),0(R15)     FIND '+-' OR ')'             BC10268 12210027
         JZ    OPCERR              ERR                          BC10268 12250027
* WE ALLOW STMT W/O +/- AND TREAT AS IF +0CD                            12260027
         CLI   0(R1),C')'          CLOSE (NO +N)?             BC10370   12270027
*BC10918 JNE   *+10                NO - EITHER +/-            BC10370   12280031
         JNE   MLA#104             NO - EITHER +/-            BBC10918  12281031
         MVC   0(L'SFVDEF3,R1),SFVDEF3     DFLT TO '+0CD)'    BC10370   12290027
MLA#104  DS    0H                                              BC10918  12291031
         STCM  R2,B'0001',SFVSIGN  KEEP THE SIGN FOR CALCULATIONBC10268 12300027
         AHI   R1,1                R1 -> POINT PAST +/-         BC10268 12310027
         L     R14,=A(NONBLANK)                                 BC10758 12321027
*BC10758 TRT   0(60,R1),NONBLANK  FIND NUM TO BE USED IN CALC   BC10268 12322027
         TRT   0(60,R1),0(R14)    FIND NUM TO BE USED IN CALC   BC10758 12323027
         JZ    OPCERR              ERR                          BC10268 12327027
         LR    R3,R1               R3-> START OF NUMBER         BC10268 12328027
         L     R15,=A(NUMTRT)   FIND END OF NUM                 BC10268 12329027
         TRT   0(60,R3),0(R15)     FIND END OF NUM              BC10268 12340027
         JZ    OPCERR              ERR  - NUMBER TOO LONG       BC10268 12380027
         ST    R1,SAVER1            SAVE POS FOLLOWING N IN +/- BC10268 12390027
         SR    R1,R3               R1 - LEN OF NUMBER           BC10268 12392027
         BZ    OPCERR       NO NUMB FND (MAYBE &VAR) (NOT SUPP) BC10351 12393027
*BC10370 MVC   SFVNUM,=80C' '      CLEAR WITH BLANKS            BC10268 12394027
         AHI   R1,-1               FOR EX                       BC10268 12395027
         EX    R1,SFVUNUMV         KEEP NUMERIC OF +N           BC10268 12396027
         L     R1,SAVER1           RESTORE POS FOLLOWING +N     BC10268 12397027
*BC10758 TRT   0(60,R1),NONBLANK  FIND FUNC TO BE USED IN CALC  BC10268 12400027
         TRT   0(60,R1),0(R14)    FIND FUNC TO BE USED IN CALC  BC10758 12410027
         JZ    OPCERR              ERR                          BC10268 12450027
         LR    R3,R1               R3-> START OF FUNCTION       BC10268 12460027
         L     R15,=A(DELIM)    FIND END OF VALUE               BC10268 12470027
         TRT   0(60,R3),0(R15)     FIND END OF VALUE            BC10268 12490027
         JZ    OPCERR              ERR                          BC10268 12503027
         ST    R1,SAVER1            SAVE POS                    BC10268 12504027
         MVC   SFVFUNC,=80C' '     CLEAR WITH BLANKS           BC10447  12505027
         MVC   SFVFUNC(2),=C'CD'   SET DFLT FUNC = CD          BC10447  12506027
         SR    R1,R3               R1 - LEN OF FUNCTN           BC10268 12507027
         BZ    NOFUNC            THERE IS NO FUNCTN - USE DFLT BC10447  12508027
*BC10447 MVC   SFVFUNC,=80C' '     CLEAR WITH BLANKS            BC10268 12509027
         AHI   R1,-1               FOR EX (NO ) NEEDED          BC10268 12510027
         EX    R1,SFVUFUMV         KEEP FUNC: CD, MO, YR, WK, WDBC10268 12520027
NOFUNC   EQU   *                                               BC10447  12530027
         L     R4,=A(SFVDVADR)     R4 -> DYNAMIC VAR TABL       BC10268 12540027
SFVSVLP  DS    0H                                               BC10268 12550027
         CLC   SFVDVNAM,SFVUDVN    MATCHED ENTRY FOUND?         BC10268 12560027
         JE    SFVNX0              YES - WORK WITH THIS ENTRY   BC10268 12570027
         CLC   SFVDVNAM,=80C' '    END OF ENTRIES?              BC10268 12590027
         JE    OPCERR              YES - DYNAMIC VAR NOT DEFINEDBC10268 12600027
         AHI   R4,SFVDVELN         NO - CONT SEARCH WITH NEXT   BC10268 12610027
         J     SFVSVLP             CONT TO LOOP                 BC10268 12620027
*                                                               BC10268 12630027
DOSUBSTR EQU   *    SUPPRT SETVAR VAR1=SUBSTR(&VAR2[.],N,M)    BC10370  12640027
         L     R15,=A(AMPERSND)                                BC10370  12650027
         TRT   8(1,R1),0(R15)      FIRST SUBSTR PARAM IS VAR?  BC10370  12670027
         BZ    OPCERR              NO - NOT SUPP               BC10370  12692027
         LA    R3,1(,R1)    POINT TO VAR NAME AFT &            BC10370  12693027
         L     R15,=A(DELIM)                                   BC10370  12695027
         TRT   0(20,R3),0(R15)     FIND DELIM AFT VAR          BC10370  12696027
         BZ    OPCERR              NO - NOT SUPP               BC10370  12700027
         CLI   0(R1),C'.'          '.' DELIM?                 BC10450   12710027
*BC10918 BNE   *+8                 NO - CHK FOR COMMA         BC10450   12720031
         BNE   MLA#105             NO - CHK FOR COMMA         BBC10918  12721031
         AHI   R1,1                YES - KEEP AS PART OF VARNMBC10450   12730027
MLA#105  DS    0H                                              BC10918  12740031
         CLI   0(R1),C','          MUST BE COMMA               BC10370  12750027
         BNE   OPCERR              NO - NOT SUPP               BC10370  12760027
         SR    R1,R3                                           BC10370  12762027
         BZ    OPCERR                                          BC10370  12763027
         BCTR  R1,0                -1                          BC10370  12764027
         EX    R1,SFVUVVMV         KEEP VAR NAM:SFVUDVN        BC10370  12765027
         LA    R3,2(R1,R3)         POINT PAST COMMA TO 1ST NUM BC10370  12766027
         L     R15,=A(NUMTRT)                                  BC10370  12767027
         TRT   0(4,R3),0(R15)     FIND DELIM AFT POS           BC10370  12769027
         BZ    OPCERR              NUM TOO LONG                BC10370  12800027
         CLI   0(R1),C','          MUST BE COMMA               BC10370  12820027
         BNE   OPCERR              NO - NOT SUPP               BC10370  12830027
         SR    R1,R3                                           BC10370  12840027
         BZ    OPCERR                                          BC10370  12850027
         BCTR  R1,0                -1                          BC10370  12860027
         EX    R1,SFVUNUMV         KEEP POS NUMERIC: SFVNUM    BC10370  12870027
         LA    R3,2(R1,R3)         POINT PAST COMMA TO 2ND NUM BC10370  12880027
         TRT   0(4,R3),0(R15)     FIND DELIM AFT LEN (NUMERIC) BC10370  12900027
         BZ    OPCERR              NUM TOO LONG                BC10370  12922027
         CLI   0(R1),C')'          MUST BE CLOSE               BC10370  12924027
         BNE   OPCERR              NO - NOT SUPP               BC10370  12925027
         SR    R1,R3                                           BC10370  12927027
         BZ    OPCERR                                          BC10370  12928027
         BCTR  R1,0                -1                          BC10370  12929027
         EX    R1,SFVUNUM2         KEEP LEN NUMERIC: SFVNUM2   BC10370  12930027
         BAL   R9,INSERT                                       BC10370  12940027
         AHI   R12,80       ADD A-E FUNCS FOR SETFORM;POINT NXTBC10370  12950027
         L     R15,=A(SFVL028)                                 BC10370  12960027
         MVC   0(L'SFVL028,R12),0(R15)     SET SUBSTR STMT     BC10370  12970027
*     DC C'//* %%SET %%12345678 = %%SUBSTR &12345678 NNN MMN'  BC10370  12980027
         MVC   12(L'SFVUVAR,R12),SFVUVAR             VAR1 NM   BC10370  12990027
         MVC   33(L'SFVUDVN,R12),SFVUDVN             VAR2 NM   BC10370  13000027
         MVC   42(L'SFVNUM,R12),SFVNUM               POS       BC10370  13010027
         MVC   46(L'SFVNUM2,R12),SFVNUM2             LEN       BC10370  13020027
         BAL   R9,CHKAMPRS    CONVERT &, % VARS ON LINE TO %%  BC10370  13030027
         B     OPCFIN                                          BC10370  13040027
TRTUDVN  TRT   SFVUDVN(*-*),0(R15)   CHK FOR ALL NUMERICS      BC10370  13050027
NUMCONST EQU   *         PROCESSING SETVAR=(NUMVAL)            BC10370  13060027
         MVC   VARLINE(L'SFVUDVN),SFVUDVN                     BC10370   13100027
         B     CHKCONS2                                        BC10370  13110027
CHKCONST EQU   *         PROCESSING SETVAR=('XXXX')            BC10370  13120027
         L     R15,=A(QUOTAB)      FIND END OF QUOTD VAL       BC10370  13130027
         TRT   1(60,R3),0(R15)     FIND END OF QUOTD VAL       BC10370  13150027
         BZ    OPCERR              DIDNT FIND                  BC10370  13172027
         SR    R1,R3               CALC LEN                    BC10370  13173027
         AHI   R1,-2                        ADJUSTED FOR 'EX'  BC10370  13174027
MLA#205  DS    0H                                              BC10918  13174146
         MVC   VARLINE(*-*),1(R3) EXTRACT THE QUOTD VAL       BC10370   13175027
**       EX    R1,*-6                                          BC10370  13176046
         EX    R1,MLA#205                                      BC10918  13176146
***  WE NOW SUPPORT SETVAR VAR1=('XXX&VAR2.XXX') TYPE STMTS             13177027
***      L     R15,=A(AMPERSND)     DONT ALLOW VARS            BC10370  13178027
***      TRT   VARLINE,0(R15)      DONT ALLOW VARS            BC10370   13179027
***      BNZ   OPCERR               CURRENTLY NOT SUPPORTED    BC10370  13180027
CHKCONS2 EQU   *                                BC10370                 13190027
         BAL   R9,INSERT                                       BC10370  13200027
         AHI   R12,80       ADD A-E FUNCS FOR SETFORM;POINT NXTBC10370  13210027
         MVC   0(L'SETSTMT,R12),SETSTMT      SET STMT PREFIX   BC10370  13220027
         MVC   L'SETSTMT(L'SFVUVAR,R12),SFVUVAR      VAR NAM   BC10370  13230027
         L     R15,=A(BLANK)                  FIND BLNK        BC10370  13240027
         TRT   L'SETSTMT(60,R12),0(R15)       FIND BLNK        BC10370  13250027
         MVI   0(R1),C'='                                      BC10370  13290027
         MVC   1(60,R1),VARLINE                                BC10370  13300027
         BAL   R9,CHKAMPRS    CONVERT &, % VARS ON LINE TO %%  BC10370  13310027
         B     OPCFIN                                          BC10370  13320027
SFVNX0   DS    0H                                               BC10268 13330027
         MVI   SFVUNIT,C' '        CALENDAR DAYS (CD)           BC10268 13340027
         CLC   =C'CD',SFVFUNC      IS FUNC=CD ?                 BC10268 13350027
         JE    SFVNX0X             YES - GENERATE THE CARDS     BC10268 13360027
         MVI   SFVUNIT,C'Y'        TRY A YEAR (YR)              BC10268 13370027
         CLC   =C'YR',SFVFUNC      IS FUNC=YR ?                 BC10268 13380027
         JE    SFVNX0X             YES - GENERATE THE CARDS     BC10268 13390027
         MVI   SFVUNIT,C'M'        TRY A MONTH (MO)             BC10268 13400027
         CLC   =C'MO',SFVFUNC      IS FUNC=MO ?                 BC10268 13410027
         JE    SFVNX0X             YES - GENERATE THE CARDS     BC10268 13420027
         MVI   SFVUNIT,C' '        TRY A WEEK (7* DAYS)         BC10268 13430027
         CLC   =C'WK',SFVFUNC      IS FUNC=WK ?                 BC10268 13440027
         JE    SFVNX0D                                          BC10268 13450027
         MVI   SFVUNIT,C' '        SIGN NO UNIT (DAYS)          BC10268 13460027
         CLC   =C'WD',SFVFUNC      IS FUNC=WD ?                 BC10268 13470027
         JE    SFVNX0X             YES -                        BC10268 13480027
         JNE   OPCERR              NO - ERROR                   BC10268 13500027
SFVNX0D  DS    0H                                               BC10268 13510027
         LHI   R2,0                START WITH SINGLE CHAR NUM   BC10268 13520027
         CLI   SFVNUM+1,C' '       IS IT SINGLE DIGIT NUM?      BC10268 13530027
         JE    SFVNX0P             YES - PACK IT                BC10268 13540027
         AHI   R2,1                ASSUME DOUBLE DIGIT          BC10268 13550027
         CLI   SFVNUM+2,C' '       IS IT DOUBLE DIGIT NUM?      BC10268 13560027
         JE    SFVNX0P             YES - PACK IT                BC10268 13570027
         AHI   R2,1                NO - THREE DIGIT             BC10268 13580027
SFVNX0P  DS    0H                                               BC10268 13590027
         EX    R2,SFVNX0E          PACK IT                      BC10268 13600027
         CVB   R1,WORK                                          BC10268 13610027
         MHI   R1,7                MULTIPLE WEEKS TO GET DAYS   BC10268 13620027
         CVD   R1,WORK                                          BC10268 13630027
         UNPK  SFVNUM,WORK                                      BC10268 13640027
         OI    SFVNUM+L'SFVNUM-1,X'F0'                          BC10268 13650027
*                                                               BC10268 13660027
SFVNX0X  DS    0H                                               BC10268 13670027
         CLC   =C'OCTIME',SFVUDVN  IS IT BASED ON OCTIME ?      BC10320 13680027
         JE    SFVNOCT             YES - PROCESS                BC10320 13690027
         CLC   =C'OCDATE',SFVUDVN  IS IT BASED ON OCDATE ?      BC10320 13700027
         JE    SFVNX0A             YES - PROCESS                BC10320 13710027
         CLC   =C'OC',SFVUDVN      IS IT BASED ON OC* ?         BC10320 13720027
         JE    SFVNX1              YES - PROCESS                BC10320 13730027
         CLC   =C'OP',SFVUDVN      IS IT BASED ON OP* ?         BC10320 13750027
         JE    OPCERR              YES - ERROR - NOT SUPPORTED  BC10320 13760027
         CLC   =C'OL',SFVUDVN      IS IT BASED ON OL* ?         BC10320 13780027
         JE    OPCERR              YES - ERROR - NOT SUPPORTED  BC10320 13790027
         CLC   =C'OX',SFVUDVN      IS IT BASED ON OX* ?         BC10320 13810027
         JE    OPCERR              YES - ERROR - NOT SUPPORTED  BC10320 13820027
         CLC   =C'O',SFVUDVN       IS IT BASED ON O* ?          BC10320 13830027
         JE    SFVNX0A             YES - PROCESS                BC10320 13840027
         CLC   =C'CDATE',SFVUDVN   IS IT BASED ON CDATE ?       BC10320 13850027
         JE    SFVNX0A             YES - PROCESS                BC10320 13860027
         CLC   =C'CTIME',SFVUDVN   IS IT BASED ON CTIME ?       BC10320 13870027
         JE    SFVNOCT             YES - PROCESS                BC10320 13880027
         CLC   =C'CHHMM',SFVUDVN   IS IT BASED ON CTIME ?       BC10351 13890027
         JE    SFVNOCT             YES - PROCESS                BC10351 13900027
         CLC   =C'C',SFVUDVN       IS IT BASED ON C ?           BC10320 13910027
         JE    SFVNX0A             YES - PROCESS                BC10320 13920027
         J     OPCERR             NO MORE PARAMETERS- NEXT CARD BC10320 13940027
SFVNX0A  DS    0H                                               BC10268 13950027
         CLC   =C'WD',SFVFUNC      IS FUNC=WD ?                 BC10268 13960027
         JE    SFVNX0W             PROCESS WD CALCULATION       BC10320 13970027
         BAL   R9,INSERT                                        BC10268 13980027
         AHI   R12,80        ADD A-E FUNCS FOR SETFORM;POINT NXTBC10268 13990027
*BC10320 CLC   =C'CDATE',SFVUDVN   IS IT BASED ON CDATE ?       BC10268 14000027
         CLI   SFVUDVN,C'O'  IS IT BASED ON O???? ? - USE $ODATEBC10268 14010027
         JNE   SFVNX0B             NO - C???? - USE $DATE       BC10268 14020027
         L     R15,=A(SFVL001)     CARD TO INSERT               BC10268 14030027
         MVC   0(L'SFVL001,R12),0(R15)        SET STMT PREFIX   BC10268 14040027
         LR    R1,R12              R1 -> LINE IN BUILD          BC10268 14050027
         AHI   R1,L'SFVL001        R1-> NEXT CHAR TO BUILD LINE BC10268 14060027
         J     SFVNX0C             WITH WD IT IS ERROR          BC10268 14070027
SFVNX0B  DS    0H                                               BC10268 14080027
         L     R15,=A(SFVL018)     CARD TO INSERT               BC10268 14090027
         MVC   0(L'SFVL018,R12),0(R15)        SET STMT PREFIX   BC10268 14100027
         LR    R1,R12              R1 -> LINE IN BUILD          BC10268 14110027
         AHI   R1,L'SFVL018        R1-> NEXT CHAR TO BUILD LINE BC10268 14120027
SFVNX0C  DS    0H                                               BC10268 14130027
         MVC   0(L'SFVSIGN,R1),SFVSIGN PUT THE SIGN             BC10268 14140027
         AHI   R1,L'SFVSIGN       R1-> AFTER THE SIGN           BC10268 14150027
         CLI   SFVUNIT,C' '       IS DAYS?                      BC10268 14160027
         JE    SFVNX0Y            YES - JUST SKIP UNIT          BC10268 14170027
         MVC   0(1,R1),SFVUNIT    NO - PUT THE RIGHT UNIT       BC10268 14180027
         AHI   R1,1               CONT OVER IT                  BC10268 14190027
SFVNX0Y  DS    0H                                               BC10268 14200027
         MVC   0(L'SFVNUM,R1),SFVNUM  PUT THE NUMBER            BC10268 14210027
         J     SFVBLD             NOW GO AND BUILD THE SET CARD BC10268 14220027
SFVNX0W  DS    0H                                               BC10268 14230027
*BC10320 CLC   =C'CDATE',SFVUDVN   IS IT BASED ON CDATE ?       BC10268 14240027
*BC10320 JE    OPCERR              WITH WD IT IS ERROR          BC10268 14250027
         CLI   SFVUDVN,C'O'  IS IT BASED ON O???? ? - USE $ODATEBC10320 14260027
         JNE   SFVNX0W4            NO - C???? - USE $DATE       BC10320 14270027
         BAL   R9,INSERT                                        BC10268 14280027
         AHI   R12,80        ADD A-E FUNCS FOR SETFORM;POINT NXTBC10268 14290027
         L     R15,=A(SFVL016)     CARD TO INSERT               BC10268 14300027
         MVC   0(L'SFVL016,R12),0(R15)        SET STMT PREFIX   BC10268 14310027
         LR    R1,R12              R1 -> LINE IN BUILD          BC10268 14320027
         AHI   R1,L'SFVL016        R1-> NEXT CHAR TO BUILD LINE BC10268 14330027
*BC10448 JNE   SFVNX0W5            NO - C???? - USE $DATE       BC10320 14340027
         B     SFVNX0W5            CONTINUE WITH +N             BC10448 14341027
SFVNX0W4 DS    0H                                               BC10320 14342027
         BAL   R9,INSERT                                        BC10268 14343027
         AHI   R12,80        ADD A-E FUNCS FOR SETFORM;POINT NXTBC10268 14344027
         L     R15,=A(SFVL027)     CARD TO INSERT               BC10268 14345027
         MVC   0(L'SFVL027,R12),0(R15)        SET STMT PREFIX   BC10268 14346027
         LR    R1,R12              R1 -> LINE IN BUILD          BC10268 14347027
         AHI   R1,L'SFVL027        R1-> NEXT CHAR TO BUILD LINE BC10268 14348027
SFVNX0W5 DS    0H                                               BC10320 14349027
         CLI   SFVNUM,C'0'         IS IT 0 VALUE ?              BC10320 14350027
         JE    SFVNX0W0            YES - DON'T USE WCALC        BC10320 14360027
         MVC   0(L'SFVSIGN,R1),SFVSIGN PUT THE SIGN             BC10268 14370027
         AHI   R1,L'SFVSIGN       R1-> AFTER THE SIGN           BC10268 14380027
         MVC   0(L'SFVNUM,R1),SFVNUM  PUT THE NUMBER            BC10268 14390027
         AHI   R1,L'SFVNUM+1      R1-> AFTER THE SIGN           BC10268 14400027
         J     SFVNX0W3           NOW GO AND BUILD THE SET CARD BC10320 14410027
SFVNX0W0 DS    0H                                               BC10320 14420027
         CLI   SFVSIGN,C'-'        IS IT BACKWARD?              BC10320 14430027
         JE    SFVNX0W1            YES - DON'T USE WCALC        BC10320 14440027
         MVI   0(R1),C'>'          SIGN NEXT WORK DAY           BC10320 14450027
         J     SFVNX0W2           NOW GO AND BUILD THE SET CARD BC10320 14460027
SFVNX0W1 DS    0H                                               BC10320 14470027
         MVI   0(R1),C'<'          SIGN NEXT WORK DAY           BC10320 14480027
SFVNX0W2 DS    0H                                               BC10320 14490027
         AHI   R1,1+1             R1-> AFTER THE SIGN           BC10320 14500027
SFVNX0W3 DS    0H                                               BC10320 14510027
         MVC   0(8,R1),CALENDAR   COPY DEFAULT CALENDAR         BC10268 14520027
         J     SFVBLD             NOW GO AND BUILD THE SET CARD BC10268 14530027
SFVNX1   DS    0H                                               BC10268 14540027
SFVNX2   DS    0H                                               BC10268 14550027
         BAL   R9,INSERT                                        BC10268 14560027
         AHI   R12,80        ADD A-E FUNCS FOR SETFORM;POINT NXTBC10268 14570027
         L     R15,=A(SFVL006)     CARD TO INSERT               BC10268 14580027
         MVC   0(L'SFVL006,R12),0(R15)        SET STMT PREFIX   BC10268 14590027
         BAL   R9,INSERT                                        BC10268 14600027
         AHI   R12,80        ADD A-E FUNCS FOR SETFORM;POINT NXTBC10268 14610027
         L     R15,=A(SFVL007)     CARD TO INSERT               BC10268 14620027
         MVC   0(L'SFVL007,R12),0(R15)        SET STMT PREFIX   BC10268 14630027
         BAL   R9,INSERT                                        BC10268 14640027
         AHI   R12,80        ADD A-E FUNCS FOR SETFORM;POINT NXTBC10268 14650027
         L     R15,=A(SFVL008)     CARD TO INSERT               BC10268 14660027
         MVC   0(L'SFVL008,R12),0(R15)        SET STMT PREFIX   BC10268 14670027
         BAL   R9,INSERT                                        BC10268 14680027
         AHI   R12,80        ADD A-E FUNCS FOR SETFORM;POINT NXTBC10268 14690027
         L     R15,=A(SFVL009)     CARD TO INSERT               BC10268 14700027
         MVC   0(L'SFVL009,R12),0(R15)        SET STMT PREFIX   BC10268 14710027
         CLC   =C'OCFRSTC',SFVUDVN IS IT BASED ON OCFRSTC?      BC10268 14720027
         JE    SFVNX2F             YES - JUST PROCESS           BC10268 14730027
         CLC   =C'OCFRSTW',SFVUDVN IS IT BASED ON OCFRSTW?      BC10268 14740027
         JE    SFVNX2FW            YES - JUST PROCESS           BC10268 14750027
         CLC   =C'OCLASTC',SFVUDVN IS IT BASED ON OCLASTC?      BC10268 14760027
         JE    SFVNX2LC            YES - JUST PROCESS           BC10268 14770027
         CLC   =C'OCLASTW',SFVUDVN IS IT BASED ON OCLASTW?      BC10268 14790027
         JNE   OPCERR              NO - ERROR                   BC10268 14800027
SFVNX2LW DS    0H                                               BC10268 14810027
         BAL   R9,INSERT                                        BC10268 14820027
         AHI   R12,80        ADD A-E FUNCS FOR SETFORM;POINT NXTBC10268 14830027
         L     R15,=A(SFVL010)     CARD TO INSERT               BC10268 14840027
         MVC   0(L'SFVL010,R12),0(R15)        SET STMT PREFIX   BC10268 14850027
         BAL   R9,INSERT                                        BC10268 14860027
         AHI   R12,80        ADD A-E FUNCS FOR SETFORM;POINT NXTBC10268 14870027
         L     R15,=A(SFVL011)     CARD TO INSERT               BC10268 14880027
         MVC   0(L'SFVL011,R12),0(R15)        SET STMT PREFIX   BC10268 14890027
         LR    R1,R12              R1 -> LINE IN BUILD          BC10268 14900027
         AHI   R1,L'SFVL011        R1-> NEXT CHAR TO BUILD LINE BC10268 14910027
         MVC   0(8,R1),CALENDAR   COPY DEFAULT CALENDAR         BC10268 14920027
         J     SFVNX2F             CONT                         BC10268 14930027
SFVNX2FW DS    0H                                                       14940027
         BAL   R9,INSERT                                        BC10268 14950027
         AHI   R12,80        ADD A-E FUNCS FOR SETFORM;POINT NXTBC10268 14960027
         L     R15,=A(SFVL020)     CARD TO INSERT               BC10268 14970027
         MVC   0(L'SFVL020,R12),0(R15)        SET STMT PREFIX   BC10268 14980027
         LR    R1,R12              R1 -> LINE IN BUILD          BC10268 14990027
         AHI   R1,L'SFVL020        R1-> NEXT CHAR TO BUILD LINE BC10268 15000027
         MVC   0(8,R1),CALENDAR   COPY DEFAULT CALENDAR         BC10268 15010027
         J     SFVNX2F             CONT                         BC10268 15020027
SFVNX2LC DS    0H                                                       15030027
         BAL   R9,INSERT                                        BC10268 15040027
         AHI   R12,80        ADD A-E FUNCS FOR SETFORM;POINT NXTBC10268 15050027
         L     R15,=A(SFVL010)     CARD TO INSERT               BC10268 15060027
         MVC   0(L'SFVL010,R12),0(R15)        SET STMT PREFIX   BC10268 15070027
         BAL   R9,INSERT                                        BC10268 15080027
         AHI   R12,80        ADD A-E FUNCS FOR SETFORM;POINT NXTBC10268 15090027
         L     R15,=A(SFVL019)     CARD TO INSERT               BC10268 15100027
         MVC   0(L'SFVL019,R12),0(R15)        SET STMT PREFIX   BC10268 15110027
         J     SFVNX2F             CONT                         BC10268 15120027
SFVNX2F  DS    0H                                               BC10268 15130027
         CLC   =C'WD',SFVFUNC      IS FUNC=WD ?                 BC10268 15140027
         JE    SFVNX2W             YES - USE THE WCALC CALCLULATBC10268 15150027
         BAL   R9,INSERT                                        BC10268 15160027
         AHI   R12,80        ADD A-E FUNCS FOR SETFORM;POINT NXTBC10268 15170027
         L     R15,=A(SFVL012)     CARD TO INSERT               BC10268 15180027
         MVC   0(L'SFVL012,R12),0(R15)        SET STMT PREFIX   BC10268 15190027
         LR    R1,R12              R1 -> LINE IN BUILD          BC10268 15200027
         AHI   R1,L'SFVL012        R1-> NEXT CHAR TO BUILD LINE BC10268 15210027
         MVC   0(L'SFVSIGN,R1),SFVSIGN PUT THE SIGN             BC10268 15220027
         AHI   R1,L'SFVSIGN       R1-> AFTER THE SIGN           BC10268 15230027
         CLI   SFVUNIT,C' '       IS DAYS?                      BC10268 15240027
         JE    SFVNX2Y            YES - JUST SKIP UNIT          BC10268 15250027
         MVC   0(1,R1),SFVUNIT    NO - PUT THE RIGHT UNIT       BC10268 15260027
         AHI   R1,1               CONT OVER IT                  BC10268 15270027
SFVNX2Y  DS    0H                                               BC10268 15280027
         MVC   0(L'SFVNUM,R1),SFVNUM  PUT THE NUMBER            BC10268 15290027
         J     SFVBLD             NOW GO AND BUILD THE SET CARD BC10268 15300027
SFVNX2W  DS    0H                                               BC10268 15310027
         BAL   R9,INSERT                                        BC10268 15320027
         AHI   R12,80        ADD A-E FUNCS FOR SETFORM;POINT NXTBC10268 15330027
         L     R15,=A(SFVL017)     CARD TO INSERT               BC10268 15340027
         MVC   0(L'SFVL017,R12),0(R15)        SET STMT PREFIX   BC10268 15350027
         LR    R1,R12              R1 -> LINE IN BUILD          BC10268 15360027
         AHI   R1,L'SFVL017        R1-> NEXT CHAR TO BUILD LINE BC10268 15370027
         MVC   0(L'SFVSIGN,R1),SFVSIGN PUT THE SIGN             BC10268 15380027
         AHI   R1,L'SFVSIGN       R1-> AFTER THE SIGN           BC10268 15390027
         MVC   0(L'SFVNUM,R1),SFVNUM  PUT THE NUMBER            BC10268 15400027
         AHI   R1,L'SFVNUM+1      R1-> AFTER THE SIGN           BC10268 15410027
         MVC   0(8,R1),CALENDAR   COPY DEFAULT CALENDAR         BC10268 15420027
         J     SFVBLD             NOW GO AND BUILD THE SET CARD BC10268 15430027
SFVNOCT  DS    0H                                               BC10320 15440027
*                     SUPPORT TIME BASED VARIABLES              BC10320 15450027
         MVC   SFVFUNC,=C'TI'     SIGN TIME BASED VARIABLE      BC10320 15460027
         BAL   R9,INSERT                                        BC10320 15470027
         AHI   R12,80        ADD A-E FUNCS FOR SETFORM;POINT NXTBC10320 15480027
         L     R15,=A(SFVL023)     CARD TO INSERT               BC10320 15490027
         MVC   0(L'SFVL023,R12),0(R15)        SET STMT PREFIX   BC10320 15500027
         BAL   R9,INSERT                                        BC10320 15510027
         AHI   R12,80        ADD A-E FUNCS FOR SETFORM;POINT NXTBC10320 15520027
         L     R15,=A(SFVL024)     CARD TO INSERT               BC10320 15530027
         MVC   0(L'SFVL024,R12),0(R15)        SET STMT PREFIX   BC10320 15540027
         BAL   R9,INSERT                                        BC10320 15550027
         AHI   R12,80        ADD A-E FUNCS FOR SETFORM;POINT NXTBC10320 15560027
         L     R15,=A(SFVL025)     CARD TO INSERT               BC10320 15570027
         MVC   0(L'SFVL025,R12),0(R15)        SET STMT PREFIX   BC10320 15580027
         BAL   R9,INSERT                                        BC10320 15590027
         AHI   R12,80        ADD A-E FUNCS FOR SETFORM;POINT NXTBC10320 15600027
         L     R15,=A(SFVL026)     CARD TO INSERT               BC10320 15610027
         MVC   0(L'SFVL026,R12),0(R15)        SET STMT PREFIX   BC10320 15620027
         J     SFVBLDBP   CONT TO BUILD THE ACTUAL SET          BC10320 15630027
SFVNX3   DS    0H                                               BC10268 15640027
         J     OPCERR             NO MORE PARAMETERS- NEXT CARD BC10268 15660027
SFVBLD   DS    0H                                               BC10268 15670027
         BAL   R9,INSERT                                        BC10268 15680027
         AHI   R12,80        ADD A-E FUNCS FOR SETFORM;POINT NXTBC10268 15690027
         L     R15,=A(SFVL002)     CARD TO INSERT               BC10268 15700027
         MVC   0(L'SFVL002,R12),0(R15)        SET STMT PREFIX   BC10268 15710027
         BAL   R9,INSERT                                        BC10268 15720027
         AHI   R12,80        ADD A-E FUNCS FOR SETFORM;POINT NXTBC10268 15730027
         L     R15,=A(SFVL003)     CARD TO INSERT               BC10268 15740027
         MVC   0(L'SFVL003,R12),0(R15)        SET STMT PREFIX   BC10268 15750027
         BAL   R9,INSERT                                        BC10268 15760027
         AHI   R12,80        ADD A-E FUNCS FOR SETFORM;POINT NXTBC10268 15770027
         L     R15,=A(SFVL004)     CARD TO INSERT               BC10268 15780027
         MVC   0(L'SFVL004,R12),0(R15)        SET STMT PREFIX   BC10268 15790027
         BAL   R9,INSERT                                        BC10268 15800027
         AHI   R12,80        ADD A-E FUNCS FOR SETFORM;POINT NXTBC10268 15810027
         L     R15,=A(SFVL005)     CARD TO INSERT               BC10268 15820027
         MVC   0(L'SFVL005,R12),0(R15)        SET STMT PREFIX   BC10268 15830027
SFVBLDBP DS    0H                                               BC10320 15840027
         BAL   R9,INSERT                                        BC10268 15850027
         AHI   R12,80        ADD A-E FUNCS FOR SETFORM;POINT NXTBC10268 15860027
         L     R15,=A(SFVL013)     CARD TO INSERT               BC10268 15870027
         MVC   0(L'SFVL013,R12),0(R15)        SET STMT PREFIX   BC10268 15880027
         LR    R1,R12              R1 -> CARD                   BC10268 15890027
         AHI   R1,L'SFVL013        R1-> NEXT CHAR TO BUILD LINE BC10268 15900027
         MVC   0(L'SFVUVAR,R1),SFVUVAR  COPY THE VAR NAME       BC10268 15910027
         L     R14,=A(BLANK)   GET LENGTH OF NAME               BC10268 15920027
         TRT   0(9,R1),0(R14)                                   BC10268 15930027
         AHI   R1,1               R1 -> AFTER THE VAR NAME      BC10268 15970027
         MVI   0(R1),C'='         BUILD THE SET =               BC10268 15980027
         AHI   R1,2               R1 -> VALUE                   BC10268 15990027
         LA    R3,SFVDVVAL        R3 -> PATTERN                 BC10268 16000027
         LA    R15,70(,R12)       R15 -> END OF VALID CARD AREA BC10268 16010027
         LA    R14,L'SFVDVVAL-1(,R3)  R14 -> END OF PATTERN     BC10268 16020027
SFVBLDBL DS    0H                                               BC10268 16030027
         NI    FLAGSCAN,X'FF'-$SFVPER     CLEAR DOT FLAG        BC10268 16040027
         CLI   0(R14),C' '        IS IT STILL BLANK ?           BC10268 16050027
         JNE   SFVBLDL            NO - START THE BUILD PROCESS  BC10268 16060027
         BCT   R14,SFVBLDBL       BACK ONE CHAR AND CONT        BC10268 16070027
SFVBLDL  DS    0H                                               BC10268 16080027
         NI    FLAGSCAN,X'FF'-$SFVDBDT    CLEAR DOT FLAG        BC10312 16090027
SFVBLDL2 DS    0H                                               BC10312 16100027
         CR    R3,R14             IS IT OVER LAST PATTERN CHAR ?BC10268 16110027
         JH    SFVBLDE            END OF BUILD                  BC10268 16120027
         CR    R1,R15             IS IT OVER END OF CARD ?      BC10268 16130027
         JH    SFVBLDE            END OF BUILD                  BC10268 16140027
         CLC   SFVFUNC,=C'TI'     IS IT A TIME BASED VAR?       BC10320 16150027
         JE    SFVBLDT            YES - LOOK FOR HH MM SS       BC10320 16160027
         CLC   =C'CC',0(R3)       IS THAT CC (CENTURY)?         BC10268 16170027
         JNE   SFVBLDY            NO - CONT                     BC10268 16180027
         MVC   0(4,R1),=C'%%1.'   YES  PUT THE VAR FOR IT       BC10268 16190027
         OI    FLAGSCAN,$SFVPER   INDICATE LAST HAS .           BC10268 16200027
         AHI   R1,4               CONT                          BC10268 16210027
         AHI   R3,2               CONT                          BC10268 16220027
         J     SFVBLDL            CONT                          BC10268 16230027
SFVBLDY  DS    0H                                               BC10268 16240027
         CLC   =C'YY',0(R3)       IS THAT YY ?                  BC10268 16250027
         JNE   SFVBLDM            NO - CONT                     BC10268 16260027
         MVC   0(4,R1),=C'%%2.'   YES  PUT THE VAR FOR IT       BC10268 16270027
         OI    FLAGSCAN,$SFVPER   INDICATE LAST HAS .           BC10268 16280027
         AHI   R1,4               CONT                          BC10268 16290027
         AHI   R3,2               CONT                          BC10268 16300027
         J     SFVBLDL            CONT                          BC10268 16310027
SFVBLDM  DS    0H                                               BC10268 16320027
         CLC   =C'MM',0(R3)       IS THAT MM ?                  BC10268 16330027
         JNE   SFVBLDJ            NO - CONT                     BC10268 16340027
         MVC   0(4,R1),=C'%%3.'   YES  PUT THE VAR FOR IT       BC10268 16350027
         OI    FLAGSCAN,$SFVPER   INDICATE LAST HAS .           BC10268 16360027
         AHI   R1,4               CONT                          BC10268 16370027
         AHI   R3,2               CONT                          BC10268 16380027
         J     SFVBLDL            CONT                          BC10268 16390027
SFVBLDJ  DS    0H                                               BC10268 16400027
         CLC   =C'WW',0(R3)       IS THAT 2 BYT WEEK#?          BC10320 16410027
         JNE   SFVBLD3            NO - CONT                     BC10320 16420027
         ST    R3,SAVER3                                        BC10320 16430027
         ST    R14,SAVER14                                      BC10320 16440027
         BAL   R9,INSERT          ADD AN EXTRA LINE AFTER CUR   BC10320 16450027
         AHI   R11,1         ADJUST LINE CNT (2 CONSEC INSRTS) BC10360  16460027
         BAL   R9,INSERT          ADD ANOTHER ONE               BC10320 16470027
         L     R3,SAVER3                                        BC10320 16480027
         L     R14,SAVER14                                      BC10320 16490027
         MVC   160(80,R12),0(R12) COPY CURRENT VALUE            BC10320 16500027
         MVC   0(80,R12),=80C' '  CLEAR OLD LINE                BC10320 16510027
         L     R9,=A(SFVL021)     CARD TO INSERT                BC10320 16520027
         MVC   0(L'SFVL021,R12),0(R9)         ADD 1ST CALC      BC10320 16530027
         L     R9,=A(SFVL022)     CARD TO INSERT                BC10320 16540027
         MVC   80(L'SFVL022,R12),0(R9)        ADD 2ND CALC      BC10320 16550027
         AHI   R12,160            R12 -> OVER 2 NEW LINES       BC10320 16560027
         BCTR  R11,0             READJUST THE LINE CNT         BC10360  16570027
         AHI   R1,160             R1 -> IN THE NEW LOCATION OF  BC10320 16580027
         AHI   R15,160            R15 -> END - TOO              BC10320 16590027
         MVC   0(4,R1),=C'%%8.'   YES  PUT THE VAR FOR IT       BC10320 16600027
         OI    FLAGSCAN,$SFVPER   INDICATE LAST HAS .           BC10320 16610027
         AHI   R1,4               CONT                          BC10320 16620027
         AHI   R3,2               CONT                          BC10320 16630027
         J     SFVBLDL            CONT                          BC10320 16640027
SFVBLD3  DS    0H                                               BC10320 16650027
         CLC   =C'DDD',0(R3)      IS THAT DDD ?                 BC10268 16660027
         JNE   SFVBLDD            NO - CONT                     BC10268 16670027
         ST    R3,SAVER3                                        BC10268 16680027
         ST    R14,SAVER14                                      BC10268 16690027
         BAL   R9,INSERT          ADD AN EXTRA LINE AFTER CUR   BC10268 16700027
         AHI   R11,1         ADJUST LINE CNT (2 CONSEC INSRTS) BC10360  16710027
         BAL   R9,INSERT          ADD ANOTHER ONE               BC10268 16720027
         L     R3,SAVER3                                        BC10268 16730027
         L     R14,SAVER14                                      BC10268 16740027
         MVC   160(80,R12),0(R12) COPY CURRENT VALUE            BC10268 16750027
         MVC   0(80,R12),=80C' '  CLEAR OLD LINE                BC10268 16760027
         L     R9,=A(SFVL014)     CARD TO INSERT                BC10268 16770027
         MVC   0(L'SFVL014,R12),0(R9)         ADD 1ST CALC      BC10268 16780027
         L     R9,=A(SFVL015)     CARD TO INSERT                BC10268 16790027
         MVC   80(L'SFVL015,R12),0(R9)        ADD 2ND CALC      BC10268 16800027
         AHI   R12,160            R12 -> OVER 2 NEW LINES       BC10268 16810027
         BCTR  R11,0             READJUST THE LINE CNT         BC10360  16820027
         AHI   R1,160             R1 -> IN THE NEW LOCATION OF  BC10268 16830027
         AHI   R15,160            R15 -> END - TOO              BC10268 16840027
         MVC   0(4,R1),=C'%%6.'   YES  PUT THE VAR FOR IT       BC10268 16850027
         OI    FLAGSCAN,$SFVPER   INDICATE LAST HAS .           BC10268 16860027
         AHI   R1,4               CONT                          BC10268 16870027
         AHI   R3,3               CONT                          BC10268 16880027
         J     SFVBLDL            CONT                          BC10268 16890027
SFVBLDD  DS    0H                                               BC10268 16900027
         CLC   =C'DD',0(R3)       IS THAT DD ?                  BC10268 16910027
         JNE   SFVBLDB            NO - CONT                     BC10268 16920027
         MVC   0(4,R1),=C'%%4.'   YES  PUT THE VAR FOR IT       BC10268 16930027
         OI    FLAGSCAN,$SFVPER   INDICATE LAST HAS .           BC10268 16940027
         AHI   R1,4               CONT                          BC10268 16950027
         AHI   R3,2               CONT                          BC10268 16960027
         J     SFVBLDL            CONT                          BC10268 16970027
SFVBLDT  DS    0H                                               BC10320 16980027
         CLC   =C'HH',0(R3)       IS THAT HH ?                  BC10320 16990027
         JNE   SFVBLDTM           NO - CONT                     BC10320 17000027
         MVC   0(4,R1),=C'%%1.'   YES  PUT THE VAR FOR IT       BC10320 17010027
         OI    FLAGSCAN,$SFVPER   INDICATE LAST HAS .           BC10320 17020027
         AHI   R1,4               CONT                          BC10320 17030027
         AHI   R3,2               CONT                          BC10320 17040027
         J     SFVBLDL            CONT                          BC10320 17050027
SFVBLDTM DS    0H                                               BC10320 17060027
         CLC   =C'MM',0(R3)       IS THAT MM ?                  BC10320 17070027
         JNE   SFVBLDTS           NO - CONT                     BC10320 17080027
         MVC   0(4,R1),=C'%%2.'   YES  PUT THE VAR FOR IT       BC10320 17090027
         OI    FLAGSCAN,$SFVPER   INDICATE LAST HAS .           BC10320 17100027
         AHI   R1,4               CONT                          BC10320 17110027
         AHI   R3,2               CONT                          BC10320 17120027
         J     SFVBLDL            CONT                          BC10320 17130027
SFVBLDTS DS    0H                                               BC10320 17140027
         CLC   =C'SS',0(R3)       IS THAT SS ?                  BC10320 17150027
         JNE   SFVBLDB            NO - CONT                     BC10320 17160027
         MVC   0(4,R1),=C'%%3.'   YES  PUT THE VAR FOR IT       BC10320 17170027
         OI    FLAGSCAN,$SFVPER   INDICATE LAST HAS .           BC10320 17180027
         AHI   R1,4               CONT                          BC10320 17190027
         AHI   R3,2               CONT                          BC10320 17200027
         J     SFVBLDL            CONT                          BC10320 17210027
SFVBLDB  DS    0H                                               BC10268 17220027
         CLI   0(R3),C' '         IS THAT A BLANK ?             BC10268 17230027
         JNE   SFVBLDR            NO - CONT                     BC10268 17240027
         MVC   0(7,R1),=C'%%BLANK'     YES  PUT THE VAR FOR IT  BC10268 17250027
         AHI   R1,7               CONT                          BC10268 17260027
         LHI   R9,0               START WITH 0 BLANK            BC10268 17270027
SFVBLDB2 DS    0H                                               BC10268 17280027
         AHI   R9,1               ADD PREVIOUS TO COUNT         BC10268 17290027
         AHI   R3,1               NEXT CHAR                     BC10268 17300027
         CLI   0(R3),C' '         MORE BLANKS?                  BC10268 17310027
         JE    SFVBLDB2                                         BC10268 17320027
         CHI   R9,1               MORE THAN SINGLE BLANK ?      BC10268 17330027
         JNH   SFVBLDB3                                         BC10268 17340027
         CVD   R9,WORK             CONVERT TO PACK FORMAT       BC10268 17350027
         UNPK  0(2,R1),WORK+6(2)   CONVERT TO CHARACTER         BC10268 17360027
         OI    1(R1),X'F0'         ZONED SIGN                   BC10268 17370027
         AHI   R1,2               NEXT CHAR                     BC10268 17380027
SFVBLDB3 DS    0H                                               BC10268 17390027
         MVC   0(1,R1),=C'.'           YES  PUT THE VAR FOR IT  BC10268 17400027
         OI    FLAGSCAN,$SFVPER   INDICATE LAST HAS .           BC10268 17410027
         AHI   R1,1               CONT                          BC10268 17420027
         J     SFVBLDL            CONT                          BC10268 17430027
SFVBLDR  DS    0H                                               BC10268 17440027
         TM    FLAGSCAN,$SFVPER   WAS LAST . ?                  BC10268 17450027
         JNO   SFVBLDR1           NO - CONT                     BC10268 17460027
         CLI   0(R3),C'.'         IS THAT ANOTHER DOT?          BC10312 17470027
         JNE   SFVBLDR2           YES - KEEP FLAG ON            BC10312 17480027
         OI    FLAGSCAN,$SFVDBDT  MARK DOUBLE DOTS              BC10312 17490027
         J     SFVBLDR3           CONT AND TAKE 2ND DOT         BC10312 17500027
SFVBLDR2 DS    0H                                               BC10312 17510027
*BC10433 AHI   R1,-1              BACK TO .                     BC10268 17520027
         BCTR  R1,0               BACK TO .            BC10268 BC10433  17530027
         ST    R1,SAVER1          SAVE FOR TRT                  BC10268 17540027
         L     R9,=A(SEPTAB)      GET SEPARATORS TABL           BC10268 17550027
         TRT   0(1,R3),0(R9)      IS NEXT CHAR A SEPARATOR?     BC10268 17560027
         L     R1,SAVER1          RESTORE FOR CONT PROCESSING   BC10268 17600027
         JNZ   SFVBLDR3           YES - CONTINUE                BC10312 17610027
         MVC   0(3,R1),=C'%%.'    PUT THE %% SEP                BC10268 17620027
         AHI   R1,3               OVER THE SEP                  BC10268 17630027
SFVBLDR1 DS    0H                                               BC10268 17640027
         TM    FLAGSCAN,$SFVDBDT  WAS LAST A DOUBLE DOT?        BC10312 17650027
         JNO   SFVBLDR3           NO - CONT                     BC10312 17660027
*BC10433 AHI   R1,-1              BACK TO .                     BC10312 17670027
         BCTR  R1,0               BACK TO .            BC10312 BC10433  17680027
         NI    FLAGSCAN,X'FF'-$SFVDBDT    CLEAR . FLAG          BC10312 17690027
SFVBLDR3 DS    0H                                               BC10312 17700027
         MVC   0(1,R1),0(R3)      TAKE 1 CHAR                   BC10268 17710027
         NI    FLAGSCAN,X'FF'-$SFVPER     CLEAR . FLAG          BC10268 17720027
         AHI   R1,1               CONT                          BC10268 17730027
         AHI   R3,1               CONT                          BC10268 17740027
         J     SFVBLDL2           CONT WITHOUT TURNING OFF DBDT BC10312 17750027
SFVBLDE  DS    0H                                               BC10268 17760027
         TM    FLAGSCAN,$SFVPER   WAS LAST . ?                  BC10268 17770027
         JNO   OPCFIN             NO - CONT                     BC10268 17780027
*BC10433 AHI   R1,-1              BACK TO .                     BC10268 17790027
         BCTR  R1,0               BACK TO .          BC10268   BC10433  17800027
         MVC   0(3,R1),=80C' '    CLEAR WITH BLANKS             BC10268 17810027
         NI    FLAGSCAN,X'FF'-$SFVPER     CLEAR . FLAG          BC10268 17820027
         J     OPCFIN                                           BC10268 17830027
SFVDVNMV MVC   SFVDVAR(*-*),0(R3) COPY THE DYNAMIC VAR NAME     BC10268 17840027
SFVDVNR9 MVC   0(*-*,R9),0(R3) COPY THE DYNAMIC VAR NAME        BC10276 17850027
SFVDVVMV MVC   SFVDVVAL(*-*),0(R3) COPY THE DYNAMIC VAR VALUE   BC10268 17860027
SFVUVNMV MVC   SFVUVAR(*-*),0(R3) COPY THE VAR NAME             BC10268 17870027
SFVUVVMV MVC   SFVUDVN(*-*),0(R3) COPY THE DYNAMIC VAR USED     BC10268 17880027
SFVUNUMV MVC   SFVNUM(*-*),0(R3)  COPY THE NUMBER               BC10268 17890027
SFVUNUM2 MVC   SFVNUM2(*-*),0(R3)  COPY THE NUMBER (SUBSTR LEN) BC10370 17900027
SFVUFUMV MVC   SFVFUNC(*-*),0(R3)  COPY THE FUNCTION            BC10268 17910027
SFVNX0E  PACK  WORK,SFVNUM(*-*)                                 BC10268 17920027
         DROP  R4                                               BC10268 17930027
*                                                                       17940027
OPCFETCH LA    R1,7(,R1)          POINT PAST FETCH                      17950027
OPCFET   CLC   =C'MEMBER=',0(R1)  LOOK FOR MEMBR KEYWORD                17960027
         BE    OPCMEMBR                                                 17970027
         LA    R1,1(,R1)                                                17980027
         BCT   R15,OPCFET                                               17990027
         B     OPCFIN             MEMBR NOT ON THIS CARD, TRY NEXT      18000027
OPCMEMBR LA    R15,7(,R1)            POINT PAST MEMBER=                 18010027
         CLI   0(R15),C'('         GET PAST PAREN             BC10351   18020027
*BC10918 BNE   *+8                                            BC10351   18030031
         BNE   MLA#106                                        BBC10918  18031031
         AHI   R15,1                                          BC10351   18040027
MLA#106  DS    0H                                              BC10918  18041031
*BC10351 L     R2,=A(COMMABLK)                                 WC0225   18050027
         L     R2,=A(PARCOMA)      BLNK, COMMA, PARENS        BC10351   18060027
         TRT   0(16,R15),0(R2)     FIND BLNK OR COMMA (8+&VAR) WC0225   18062027
         BZ    OPCERR                                                   18066027
         LR    R2,R1                 SAVE ADDR                          18067027
         SR    R1,R15                   LENGTH OF MEMBR NAME            18068027
         BCTR  R1,0                                                     18069027
         MVC   OPCMEMB,=80C' '                                          18070027
         EX    R1,MVCMEMB                                               18080027
         CLI   0(R2),C','            IS IT CONTINUATION                 18090027
         BNE   FNOCOMP               NO                                 18100027
         OI    FLAGS,FETCHCON        YES - SET FLAG                     18110027
         LA    R1,1(,R2)             RESTORE ADDRESS AFTER ','          18120027
         LA    R15,55                                                   18130027
         B     OPCLOOP               LOOK FOR COMP=                     18140027
FNOCOMP  LA    R12,80(,R12)        POINT TO NEXT CARD                   18150027
         BAL   R9,INSERT                                                18160027
         MVC   80(80,R12),0(R12)                                        18170027
         MVC   0(80,R12),=80C' '                                        18180027
*BC10370 MVC   0(L'INCLIB,R12),INCLIB                                   18190027
         L     R1,=A(INCLIB)                                BC10370     18200027
         MVC   0(L'INCLIB,R12),0(R1)                        BC10370     18210027
         MVC   L'INCLIB(L'OPCMEMB,R12),OPCMEMB                          18220027
         BAL   R9,CHKAMPRS           CONVERT ANY VARIABLES IN FETCH NAM 18230027
         TM    FLAGS,FETCHCON                                           18240027
         BNO   OPCFIN                                                   18250027
         NI    FLAGS,X'FF'-FETCHCON  RESET FLAG                         18260027
         B     OPCEND                     WRITE LAST LABEL              18270027
MVCMEMB  MVC   OPCMEMB(*-*),0(R15)                                      18280027
*                                                                       18290027
OPCSRCH  LA    R1,7(,R1)        POINT PAST KEYWORD SEARCH/TABLE         18300027
OPCSRC   CLC   =C'NAME=',0(R1)  LOOK FOR NAME= KEYWORD                  18310027
         BE    OPCNAME                                                  18320027
         LA    R1,1(,R1)                                                18330027
         BCT   R15,OPCSRC                                               18340027
         B     OPCERR           ERROR                                   18360027
OPCNAME  L     R7,=A(TABLE)       R7 POINTS TO TABL-NAME TABL WC0237    18370027
         LA    R1,5(,R1)           POINT PAST NAME=             BC10351 18380027
         CLI   0(R1),C' '         IS THERE JUST A BLNK? BC10268 BC10351 18400027
         BE    OPCERR               YES - ERROR                 BC10268 18410027
         CLI   0(R1),C'('          IS THERE OPEN PARENTHESIS?   BC10351 18420027
         BNE   FINDSRC0              NO                                 18430027
         LA    R1,1(,R1)           POINT PAST (                 BC10351 18440027
FINDSRC0 EQU   *            R1- POINTS TO TBL NM              BC10093   18450027
         LR    R2,R1        SAVE POINTER TO TBL NM            BC10351   18460027
         LR    R0,R7                CLEAR TBLE TO BLNKS       BC10351   18470027
         LA    R1,8*L'TABLE                                   BC10351   18480027
         SR    R14,R14                                        BC10351   18490027
         SR    R15,R15                                        BC10351   18500027
MVCLE6   MVCLE R0,R14,C' '(0)                                 BC10351   18510027
         BC    1,MVCLE6                                       BC10351   18520027
         LR    R15,R2           RE-POINT TO TBL NM            BC10351   18530027
         ZAP   SRCHCNT,=P'0'       REINIT TABL COUNT         BC10093    18540027
FINDSRCH EQU   *                                                BC10093 18550027
*BC10351 TRT   0(20,R15),PARCOMA  FIND TABLNM DELIM:CLOSPAREN,BLNK,COMA 18560027
         TRT   0(MAXTBLNM+1,R15),PARCOMA  FIND END DLM (50)     BC10351 18580027
         BZ    OPCERR              ERROR                                18602027
         LR    R2,R1              SAVE ADDR OF ',' OR ')' OR BLNK       18603027
         SR    R1,R15               LENGTH OF TABL NAME                 18604027
         BNZ   SRCHTBL              THERE IS A TABL NAME                18605027
         OI    FLAGS,SRCHCONF       NO NAME - MUST BE A CONTINUATION    18606027
         B     BLDSRCH             BUILD AUTO-EDIT                      18607027
SRCHTBL  BCTR  R1,0                                                     18608027
         CLC   =C'APPL',0(R15)                                          18610027
         BE    OPCERR              NOT SUPPORTED                        18620027
         CLC   =C'NOAPPL',0(R15)                                        18630027
         BE    SRCHIGNR            IGNORE IT                            18640027
         CLC   =C'NOGLOBAL',0(R15)                                      18650027
         BE    SRCHIGNR            IGNORE IT                            18660027
         CLC   =C'GLOBAL',0(R15)                              BC0102    18670027
         BE    SRCHIGNR            IGNORE IT                  BC0102    18680027
         MVC   VARTABON,=80C' '                                 BC10276 18690027
         EX    R1,MVCTBL           MVC VARTABON(*-*),0(R15)     BC10276 18700027
*    R1 - LENGTH FOR EX, R15 -> NAME - COPY TO 16 BLANK AREA    BC10276 18710027
*  SEARCH IN 018 TABL, AND COPY THE 8-CHAR NAME TO TABL        BC10276  18720027
         USING VARTBLDS,R9         INTERNAL VAR TBL             BC10276 18730027
         L     R9,VARTABBF         POINTER TO BUFFER FOR VARTAB BC10276 18740027
VARSCLP  DS    0H                                               BC10276 18750027
         CLC   VTOPCNM,VARTABON     IS IT THIS ENTRY?           BC10276 18760027
         JE    VARSCFND                                         BC10276 18770027
         AHI   R9,VTLEN             R6 -> NEXT ENTRY LOCATION   BC10276 18780027
         C     R9,VARTABEN          END OF LIST ?               BC10276 18790027
         JL    VARSCLP              NO - CONT TO CHECK NEXT     BC10276 18800027
         MVC   0(L'TABLE,R7),VARTABON  NOT FOUND - USE ORIG     BC10276 18810027
*BC10893 MVC   WTOWRN+19(8),MEMBER                              BC10351 18820028
         MVC   ERR01MEM(8),MEMBER      MOVE THE MEMBER NAME     BC10894 18822029
*BC10893 MVC   WTOWRN+28(16),VARTABON                           BC10351 18830028
         MVC   ERR01VAR(16),VARTABON   MOVE THE VARIABLE TAB    BC10893 18831029
*BC10893 WTO   'CTMOP1507W-XXXXXXXX YYYYYYYYYYYYYYYY MEMSYM NAME MAY NO*18840028
               T EXIST OR MAY BE INCORRECTLY RESOLVED AT RUNTIME' 10354 18850027
         L     R1,ERROR         LOAD THE DCB ADDRESS OF MSG     BC10893 18851029
         PUT   0(R1),ERROR001          WRITE THE MESSAGE        BC10893 18852029
         J     VARSCFNF             END - NOT FOUND - ERROR     BC10276 18860027
VARSCFND DS    0H                                               BC10276 18870027
         MVC   0(L'VTCTMNM,R7),VTCTMNM     COPY THE NEW NAME    BC10276 18880027
         DROP  R9                                               BC10276 18890027
*  ENTRY FOUND AND COPIED                                       BC10276 18900027
VARSCFNF DS    0H                                               BC10276 18910027
         AP    SRCHCNT,=P'1'                                            18920027
SRCHIGNR CLI   0(R2),C','          ARE THERE MORE TABL IN LIST          18930027
         BNE   BLDSRCH             NO- BUILD AUTO EDIT                  18940027
         CP    SRCHCNT,=P'8'       YES                                  18960027
         BH    OPCERR              TOO MANY                             18970027
         LA    R7,L'TABLE(,R7)      POINT TO NEXT EXP2                  18980027
         LA    R15,1(,R2)               POINT PAST COMMA                18990027
         B     FINDSRCH            KEEP FINDING MORE EXPRESSIONS        19000027
*BC10276 MVCTBL   MVC   0(*-*,R7),0(R15)    R7 - A(TABLE)               19010027
MVCTBL   MVC   VARTABON(*-*),0(R15)    KEEP ORIGNAL NAME        BC10276 19020027
*                                                                       19030027
BLDSRCH  EQU   *                                                        19040027
         CVB   R15,SRCHCNT          NUMBER OF LIBSYM STMTS              19050027
         LTR   R15,R15            EMPTY TABLE?                 BC10450  19060027
         BZ    OPCFIN               YES                        BC10450  19070027
         L     R7,=A(TABLE)       R7 POINTS TO TABL-NAM TABL WC0237     19080027
SRCHLP   EQU   *                                                        19090027
         LA    R12,80(,R12)        POINT TO NEXT CARD                   19100027
         BAL   R9,INSERT                                                19110027
         MVC   80(80,R12),0(R12)                                        19120027
         MVC   0(80,R12),=80C' '                                        19130027
         MVC   0(L'MYLIBSYM+L'MYLIBNAM,R12),MYLIBSYM            BC10276 19140027
*BC10276 MVC   0(L'LIBSYM+L'LIBNAM+L'LIBMEM,R12),LIBSYM                 19150027
         LA    R12,80(,R12)        POINT TO NEXT CARD           BC10276 19160027
         BAL   R9,INSERT                                        BC10276 19170027
         MVC   80(80,R12),0(R12)                                BC10276 19180027
         MVC   0(80,R12),=80C' '                                BC10276 19190027
*BC10276 MVC   L'LIBSYM+L'LIBNAM+L'LIBMEM(L'MEMSYM,R12),0(R7)           19200027
         MVC   MYMEMNAM,0(R7)                                   BC10276 19210027
         MVC   0(L'MYMEMSYM+L'MYMEMNAM,R12),MYMEMSYM            BC10276 19220027
*BC10276 NI    FLAGS1,X'FF'-$VARXST          RESET             BC10084  19230027
         BAL   R9,CHKAMPRS     CONVERT VARIABLES IN SEARCH NAME BC0101  19240027
*BC10276 TM    FLAGS1,$VARXST   IS THERES A VARIABLE IN NAME?   BC10084 19250027
*BC10276 BO    *+10             YES - DONT LIMIT NAME TO 8 CHAR BC10084 19260027
*BC10276 MVC   L'LIBSYM+L'LIBNAM+L'LIBMEM+8(4,R12),=80C' '      BC10084 19270027
         LA    R12,80(,R12)        POINT TO NEXT CARD           BC10351 19280027
         BAL   R9,INSERT                                        BC10351 19290027
         MVC   80(80,R12),0(R12)                                BC10351 19300027
         MVC   0(80,R12),=80C' '                                BC10351 19310027
         MVC   0(L'SUBSTR,R12),SUBSTR  CUT MYMEMSYM TO 8 CHAR   BC10351 19320027
         LA    R12,80(,R12)        POINT TO NEXT CARD           BC10276 19330027
         BAL   R9,INSERT                                        BC10276 19340027
         MVC   80(80,R12),0(R12)                                BC10276 19350027
         MVC   0(80,R12),=80C' '                                BC10276 19360027
         MVC   0(L'LIBSYM,R12),LIBSYM NOW COPY THE LINE ITSELF  BC10276 19370027
         LA    R7,L'TABLE(,R7)                                          19380027
         BCT   R15,SRCHLP                                               19390027
*BC10093 L     R15,=A(TABLE)                                    WC0237  19400027
*BC10093 MVI   0(R15),C' '  BLNK OUT TABL (FUTURE TBLS)BC0101 WC0237    19410027
*BC10093 MVC   1(8*L'TABLE-1,R15),0(R15)                 BC0101 WC0237  19420027
*BC10093 ZAP   SRCHCNT,=P'0'       REINIT TABL COUNT                    19430027
         B     OPCFIN                                                   19440027
*                                                                       19450027
OPCBEGIN LA    R1,7(,R1)           POINT PAST BEGIN                     19460027
         AHI   R15,-7              REDUCE BYTES LEFT            WC10083 19470027
         ST    R1,AFTBEGIN         SAVE ADDR AFTER BEGIN                19480027
OPCBEG   CLC   =C'ACTION=',0(R1)  LOOK FOR ACTION KEYWORD               19490027
         BE    OPCACTN                                                  19500027
         LA    R1,1(,R1)                                                19510027
         BCT   R15,OPCBEG                                               19520027
         B     OPCERR             ERROR                                 19540027
OPCACTN  NI    FLAGS,X'FF'-ACTION ACTION=0 MEANS INCLUDE                19550027
         OI    FLAGS,FOUND        ACTION FOUND                          19560027
         LA    R1,7(,R1)          POINT PAST ACTION=                    19570027
         AHI   R15,-7              REDUCE BYTES LEFT            WC10083 19580027
         CLC   =C'INCLUDE',0(R1)                                        19590027
         BE    ACTNOK                                                   19600027
         CLC   =C'EXCLUDE',0(R1)                                        19610027
         BE    ACTNOKEX            HANDLE EXCLUDE               BC10268 19620027
         CLC   =C'NOSCAN',0(R1)    IS IN ACTION=NOSCAN ?        BC10268 19630027
         BE    ACTNOSC             YES - HANDLE THAT            BC10268 19640027
         CLC   =C'SCAN',0(R1)    IS IN ACTION=SCAN ?            BC10758 19650027
         BE    ACTNSCAN             IGNORE - THIS IS DFLT       BC10758 19660027
         BNE   OPCERR                                                   19680027
ACTNOKEX DS    0H                                               BC10268 19690027
         OI    FLAGS,ACTION        SET EXCLUDE                          19700027
ACTNOK   LA    R1,7(,R1)           POINT PAST INCLUDE/EXCLUDE           19710027
         AHI   R15,-7              REDUCE BYTES LEFT            WC10083 19720027
         ST    R1,CURRADDR                                              19730027
         CLI   0(R1),C','          IS THERE MORE                        19740027
         BNE   ACTNONLY            NO - WRITE GOTO                      19750027
         CLC   =C',PHASE=',0(R1)   PHASE= PARAM ?                       19760027
         BNE   OPCLOOP             NO   - LOOK FOR COMP=                19770027
         LA    R1,7(,R1)           POINT PAST PHASE=                    19780027
         AHI   R15,-7              REDUCE BYTES LEFT            WC10083 19790027
         L     R2,=A(COMMABLK)                                  WC0225  19800027
         TRT   0(10,R1),0(R2)      LOOK FOR ',' OR BLNK        WC0225   19802027
         BZ    OPCERR                                                   19806027
         ST    R1,CURRADDR                                              19807027
         CLI   0(R1),C','          IS THERE MORE AFTER PHASE=           19808027
         L     R1,AFTBEGIN         GET  ADDR AFTER BEGIN                19809027
         BE    OPCLOOP             LOOK FOR COMP=                       19810027
ACTNONLY L     R1,AFTBEGIN         GET  ADDR AFTER BEGIN                19820027
         NI    FLAGS,X'FF'-FOUND       RESET ACTION FLAG                19830027
         LA    R15,60                                                   19840027
COMP1ST  CLC   =C'COMP=',0(R1)     WAS COMP= CODED FIRST                19850027
         BE    CHKCOMP             YES                                  19860027
         LA    R1,1(,R1)                                                19870027
         BCT   R15,COMP1ST                                              19880027
NOCOMP   TM    FLAGS,ACTION    NO- IS ACTION INCLUDE?                   19890027
         BNO   OPCFIN          YES-NOTHING TO DO                        19900027
         MVC   0(80,R12),=80C' '   NO- ITS EXCLUDE - CONSTRUCT GOTO     19910027
         MVC   0(L'GOTO,R12),GOTO                                       19920027
         MVC   L'GOTO(2,R12),IFCNT1      GOTO NNN1                      19930027
         MVC   L'GOTO+2(2,R12),=C'XX'   YES                             19940027
         B     OPCFIN                                                   19950027
ACTNOSC  DS    0H         HANDLE BEGIN ACTION=NOSCAN            BC10268 19960027
         LA    R12,80(,R12)        POINT TO NEXT CARD           BC10268 19970027
         BAL   R9,INSERT                                        BC10268 19980027
         MVC   80(80,R12),0(R12)                                BC10268 19990027
         MVC   0(80,R12),=80C' '   MAKE IT //*%%RESOLVE OFF     BC10268 20000027
         MVC   0(L'RESOFF,R12),RESOFF                           BC10268 20010027
         OI    FLAGSCAN,$RESOFF    MARK WE ARE IN NO RESOLVE    BC10268 20020027
ACTNSCAN EQU   *                                                BC10758 20030027
         OI    FLAGS,CHANGES       MARK MEMBR HAS BEEN CHANGED BC10268  20040027
         B     OPCFIN                                           BC10268 20050027
*                                                                       20060027
CHKCOMP  C     R1,CURRADDR                                              20070027
         BH    NOCOMP              COMP= IS JUST A COMMENT              20080027
OPCOMP   LA    R1,5(,R1)           POINT PAST COMP=                     20090027
OPCOMPC  EQU   *                                                        20100027
         LA    R15,70(,R12)         POINT TO END OF LINE                20110027
         SR    R15,R1               NUMBER OF CHARS LEFT ON LINE        20120027
         L     R14,=A(GLOBAL)    WILDCARDS: % AND * NOT ALLOWED BC10327 20130027
         EX    R15,TRTGLOBL         TRT 0(*-*,R1),0(R14)        BC10327 20140027
**??     CHANGE TO  TRT 2(*-*,R1),0(R14) TO ALLOW '%' AS FIRST VAR TYPE 20150027
*BC10327 EX    R15,TRTGLOBL         TRT 0(*-*,R1),GLOBAL                20160027
         BNZ   OPCERR              NOT SUPPORTED                        20210027
OPCMORE  MVC   VAR,=80C' '         INIT                                 20220027
*WC10026 L     R6,=A(EXP2)         CLEAR EXP2 TABL          BC0101      20230027
*WC10026 L     R7,EXP2LEN                                               20240027
         ST    R1,SAVER1           SAVE R1 TILL AFTER MVCL   WC10026    20250027
         L     R0,=A(EXP2)         CLEAR EXP2 TABL   BC0101 WC10026     20260027
         L     R1,EXP2LEN                                    WC10026    20270027
         LA    R14,0               DUMY ADDR                            20280027
         LA    R15,C' '            PAD                                  20290027
         SLL   R15,24                                                   20300027
*WC10026 MVCL  R6,R14                                                   20310027
         MVCL  R0,R14                                        WC10026    20320027
         L     R1,SAVER1        RESTORE R1 FROM BEFOR MVCL   WC10026    20330027
         L     R7,=A(EXP2)                                  BC0101      20340027
         L     R15,=A(AMPERSND)   FIND  VARIABLE            BC10091     20350027
         TRT   0(9,R1),0(R15)       FIND  VARIABLE          BC10091     20352027
         BZ    OPCERR              DIDNT FIND VARIABLE                  20356027
         LR    R15,R1           SAVE START OF VARIABLE NAME             20357027
         L     R2,=A(TRTPER)                           WC0237  WC10012  20358027
         TRT   0(20,R15),0(R2)      FIND END OF VARIABLE NAME   WC0237  20360027
         BZ    OPCERR              DIDNT FIND END OF VARIABLE           20400027
         LA    R2,1(,R1)           SAVE END ADDR OF VAR (AFTER .)       20410027
         SR    R1,R15                                                   20420027
         BCTR  R1,0                                                     20430027
         EX    R1,MVCVAR           MVC VAR(*-*),0(R15) INCL &           20440027
*BC10297 MVC   OPER,=C'EQ'         EQ                                   20450027
*BC10297 CLC   =C'.EQ.',0(R2)      OPERATOR = .EQ.                      20460027
*BC10297 BE    OPEREQ                                                   20470027
*BC10297 MVC   OPER,=C'NE'                                              20480027
         MVC   OPER,1(R2)        SAVE THE OPER FROM '.OP.'   BC10297    20490027
OPEREQ   LA    R15,4(,R2)           POINT PAST OPERATOR                 20500027
         CLI   0(R15),C'('          LIST FOR EXPRESSION2?               20510027
*BC10918 BNE   *+8                                                      20520031
         BNE   MLA#107                                         BC10918  20521031
FINDEXP2 LA    R15,1(,R15)           POINT PAST '('  (',' ON CONTINUE)  20530027
MLA#107  DS    0H                                              BC10918  20531031
FINDEXPC TRT   0(20,R15),PARCOMA    FIND END OF EXPRESSION              20540027
         BZ    OPCERR              ERROR                                20550427
         LR    R2,R1              SAVE ADDR OF ',' OR ')' OR BLNK       20550527
         SR    R1,R15                                                   20550627
         BZ    EXP2MORE            THE COMP= VARIABLE IS CONTINUED      20550727
         BCTR  R1,0                                                     20550827
         EX    R1,MVCOPER2         MVC 0(*-*,R7),0(R15)  R7=EXP2 TBL    20550927
         AP    EXP2CNT,=P'1'       ADD TO NUMBER OF EXP2 VARS           20551027
         CLI   0(R2),C','          ARE THERE MORE VARIABLES IN LIST     20552027
         BE    EXP2CONT         YES-  MORE VARIABLES                    20553027
         L     R14,=A(BLANK)      NO - CHECK IF THERES A CONTIN WC10012 20554027
         TRT   0(6,R2),0(R14)                                   WC10012 20555027
         BZ    COMPMORE               NO BLNK - ANOTHER PARAMETER ?     20559027
         NI    FLAGS,X'FF'-MORE    RESET                        BC10268 20560027
         BCTR  R1,0                                                     20570027
         CLI   0(R1),C','          CONTINUATION?                        20580027
         BNE   BUILDAE             NO - BUILD AUTO-EDIT STMTS           20590027
         OI    FLAGS,EXPCONT       YES                                  20600027
         B     BUILDAE             BUILD AUTO-EDIT                      20610027
EXP2CONT CP    EXP2CNT,=P'100'                                          20620027
         BH    OPCERR              TOO MANY                             20640027
         LA    R7,L'EXP2(,R7)      POINT TO NEXT EXP2                   20650027
         LR    R15,R2              POINT TO COMMA                       20660027
         B     FINDEXP2            KEEP FINDING MORE EXPRESSIONS        20670027
*                                                                       20680027
EXP2MORE LA    R12,80(,R12)        POINT TO NEXT JCL STMT               20690027
         BCTR  R11,0                                                    20700027
         LTR   R11,R11                                                  20710027
         BZ    OPCERR              NO MORE LINES- ERROR                 20730027
         CLC   =C'//*%OPC ',0(R12)  MAKE SURE IT CONTINUATION           20750027
         BNE   OPCERR                                                   20760027
         LA    R1,7(,R12)         POINT PAST OPC                        20770027
         L     R14,=A(NONBLANK)                                 BC10758 20780027
*BC10758 TRT   0(65,R1),NONBLANK   FIND FIRST NON-BLNK                  20790027
         TRT   0(65,R1),0(R14)     FIND FIRST NON-BLNK          BC10758 20800027
         LR    R15,R1                                                   20840027
         B     FINDEXPC                                                 20850027
*                                                                       20860027
COMPMORE L     R15,=A(OPNPAREN)                                 WC0001  20870027
         TRT   0(6,R2),0(R15)     REAL CONTINUATION OF COMP=?   WC0001  20880027
         BZ    BUILDAE                NO - SOME OTHER PARAMETER         20920027
         TM    FLAGS,MORE          ARE WE ALREADY IN MORE MODE? BC10268 20930027
         BO    CM1                 YES - R1 -> MORE AREA, UPDATEBC10268 20940027
         OI    FLAGS,MORE          SET FLAG                             20950027
         MVC   LINE,0(R12)         SAVE THE ENTIRE LINE                 20960027
         SR    R1,R12              OFFSET TO WHERE WE ARE               20970027
         LA    R1,LINE(R1)         NEW POSITION IN LINE                 20980027
CM1      DS    0H                                               BC10268 20990027
         ST    R1,MOREADDR         SAVE ADDR ON LINE                    21000027
BUILDAE  L     R7,=A(EXP2)                                   BC0101     21010027
         CVB   R15,EXP2CNT                                              21020027
         AP    GOTOCNT2,=P'1'                                           21030027
         UNPK  IFCNT2,GOTOCNT2                                          21040027
         OI    IFCNT2+1,X'F0'                                           21050027
*BC10297 CLC   =C'EQ',OPER                                              21060027
*BC10297 BNE   BUILDAE2                                                 21070027
         CLC   =C'NE',OPER                                   BC10297    21080027
         BE    BUILDAE2         ALL EXP2 VALUES MUST NE EXP1 BC10297    21090027
IF1LOOP  EQU   *   EXP1 MUST HAVE RELATION 'OP' W/ (ONE OF) EXP2 VAL(S) 21100027
         LA    R12,80(,R12)        POINT TO NEXT CARD                   21110027
         BAL   R9,INSERT                                                21120027
         MVC   80(80,R12),0(R12)                                        21130027
         MVC   0(80,R12),=80C' '                                        21140027
         MVC   0(L'IF,R12),IF                 %%IF %%                   21150027
         MVC   L'IF(L'VAR,R12),VAR                   VAR                21160027
         MVC   L'IF+L'VAR+1(L'OPER,R12),OPER              EQ/NE         21170027
         MVC   L'IF+L'VAR+L'OPER+2(L'EXP2,R12),0(R7)            EXP2    21180027
         BAL   R9,CHKAMPRS         TRANSLATE & TO %%                    21190027
         LA    R7,L'EXP2(,R7)      POINT TO NEXT EXP2                   21200027
         LA    R12,80(,R12)        POINT TO NEXT CARD                   21210027
         BAL   R9,INSERT                                                21220027
         MVC   80(80,R12),0(R12)                                        21230027
         MVC   0(80,R12),=80C' '                                        21240027
         MVC   0(L'GOTO,R12),GOTO            %%GOTO LABEL               21250027
         MVC   L'GOTO(L'IFCNT1,R12),IFCNT1                      NN      21260027
*BC10338 MVC   L'GOTO+L'IFCNT1(2,R12),=C'XX'   EXCLUDE                  21270027
*BC10338 TM    FLAGS,ACTION              IS IT EXCLUDE?                 21280027
*BC10338 BO    IFEXCLUD                       YES                       21290027
         MVC   L'GOTO+L'IFCNT1(L'IFCNT2,R12),IFCNT2    NO               21300027
*BC10338IFEXCLUD LA    R12,80(,R12)        POINT TO NEXT CARD           21310027
         LA    R12,80(,R12)        POINT TO NEXT CARD           BC10338 21320027
         BAL   R9,INSERT                                                21330027
         MVC   80(80,R12),0(R12)                                        21340027
         MVC   0(80,R12),=80C' '                                        21350027
         MVC   0(L'ELSE,R12),ELSE                                       21360027
         BCT   R15,IF1LOOP                                              21370027
FALSGOTO LA    R12,80(,R12)        POINT TO NEXT CARD                   21380027
         BAL   R9,INSERT                                                21390027
         MVC   80(80,R12),0(R12)                                        21400027
         MVC   0(80,R12),=80C' '                                        21410027
         MVC   0(L'GOTO,R12),GOTO                                       21420027
         MVC   L'GOTO(L'IFCNT1,R12),IFCNT1      GOTO NNN1               21430027
*BC10338 MVC   L'GOTO+L'IFCNT1(L'IFCNT2,R12),IFCNT2    EXCLUDE          21440027
*BC10338 TM    FLAGS,ACTION              IS IT EXCLUDE?                 21450027
*BC10338 BO    IFEXCLD3                                                 21460027
*BC10338 MVC   L'GOTO+L'IFCNT1(2,R12),=C'XX'   GOTO NNN-END             21470027
         MVC   L'GOTO+L'IFCNT1(2,R12),=C'RU'   GOTO NNN-END     BC10338 21480027
*BC10338IFEXCLD3 CVB   R15,EXP2CNT                                      21490027
         CVB   R15,EXP2CNT                                      BC10338 21500027
ENDIFLP  LA    R12,80(,R12)        POINT TO NEXT CARD                   21510027
         BAL   R9,INSERT                                                21520027
         MVC   80(80,R12),0(R12)                                        21530027
         MVC   0(80,R12),=80C' '                                        21540027
         MVC   0(L'ENDIF,R12),ENDIF                                     21550027
         BCT   R15,ENDIFLP                                              21560027
IFLABEL  LA    R12,80(,R12)        POINT TO NEXT CARD                   21570027
         BAL   R9,INSERT                                                21580027
         MVC   80(80,R12),0(R12)                                        21590027
         MVC   0(80,R12),=80C' '                                        21600027
         MVC   0(L'LABEL,R12),LABEL                                     21610027
         MVC   L'LABEL(L'IFCNT1,R12),IFCNT1                             21620027
         MVC   L'LABEL+L'IFCNT1(L'IFCNT2,R12),IFCNT2                    21630027
* ON FALSE CONDITIONS IGNORE THE BEGIN DIRECTIVE                        21640027
*        TM    FLAGS,EXPCONT      EXPECT A CONTINUATION OF COMP=        21650027
*        BO    OPCFIN              YES                                  21660027
*        LA    R12,80(,R12)    NO -POINT TO NEXT CARD                   21670027
*        BAL   R9,INSERT                                                21680027
*        MVC   80(80,R12),0(R12)                                        21690027
*        MVC   0(L'LABEL,R12),LABEL                                     21700027
*        MVC   L'LABEL(L'IFCNT1,R12),IFCNT1                             21710027
*        MVC   L'LABEL+2(5,R12),=C'FALSE'                               21720027
         ZAP   EXP2CNT,=P'0'                                            21730027
         TM    FLAGS,MORE         MORE FLAG SET?                        21740027
         BNO   BUILDCON            NO                                   21750027
*BC10268 NI    FLAGS,X'FF'-MORE    RESET                                21760027
         L     R1,MOREADDR         GET ADDR ON LINE                     21770027
         B     OPCMORE                                                  21780027
BUILDCON TM    FLAGS,EXPCONT       MORE COMP= COMING                    21790027
         BO    OPCFIN              YES - OK GO GET IT                   21800027
         TM    FLAGS,ACTION            IS IT EXCLUDE?           BC10338 21810027
         BO    SETEXCL                 .Y                       BC10338 21820027
*                                      .N, IT IS INCLUDE,       BC10338 21830027
         SH    R12,=H'80'              BUILD                    BC10338 21840027
         LA    R11,1(,R11)             %%LABEL LABEL00RU        BC10338 21850027
         BAL   R9,INSERT               %%GOTO LABEL00XX         BC10338 21860027
         LA    R12,80(,R12)                   JUST              BC10338 21870027
         MVC   0(80,R12),=80C' '              BEFORE            BC10338 21880027
         MVC   0(L'LABEL,R12),LABEL           THE               BC10338 21890027
         MVC   L'LABEL(L'IFCNT1,R12),IFCNT1   LAST              BC10338 21900027
         MVC   L'LABEL+L'IFCNT1(2,R12),=C'RU' LABEL             BC10338 21910027
         BAL   R9,INSERT                                        BC10338 21920027
         LA    R12,80(,R12)                                     BC10338 21930027
         MVC   0(80,R12),=80C' '                                BC10338 21940027
         MVC   0(L'GOTO,R12),GOTO                               BC10338 21950027
         MVC   L'GOTO(2,R12),IFCNT1                             BC10338 21960027
         MVC   L'GOTO+2(2,R12),=C'XX'                           BC10338 21970027
         B     SETACTNX                                         BC10338 21980027
SETEXCL  DS    0H                      IT IS EXCLUDE,           BC10338 21990027
         BAL   R9,INSERT               BUILD                    BC10338 22000027
         LA    R12,80(,R12)            %%GOTO LABEL00XX         BC10338 22010027
         MVC   0(80,R12),=80C' '       %%LABEL LABEL00RU        BC10338 22020027
         MVC   0(L'GOTO,R12),GOTO             JUST              BC10338 22030027
         MVC   L'GOTO(2,R12),IFCNT1           AFTER             BC10338 22040027
         MVC   L'GOTO+2(2,R12),=C'XX'         THE               BC10338 22050027
         BAL   R9,INSERT                      LAST              BC10338 22060027
         LA    R12,80(,R12)                   LABEL             BC10338 22070027
         MVC   0(80,R12),=80C' '                                BC10338 22080027
         MVC   0(L'LABEL,R12),LABEL                             BC10338 22090027
         MVC   L'LABEL(L'IFCNT1,R12),IFCNT1                     BC10338 22100027
         MVC   L'LABEL+L'IFCNT1(2,R12),=C'RU'                   BC10338 22110027
*                                                               BC10338 22120027
SETACTNX DS    0H                                               BC10338 22130027
         TM    FLAGS,FETCHCON      NO - WAS FETCH CONTINUED?            22140027
         BO    FNOCOMP                                                  22150027
         B     OPCFIN              NO - KEEP GOING                      22160027
BUILDAE2 EQU   *                                                        22170027
IF2LOOP  LA    R12,80(,R12)        POINT TO NEXT CARD                   22180027
         BAL   R9,INSERT                                                22190027
         MVC   80(80,R12),0(R12)                                        22200027
         MVC   0(80,R12),=80C' '                                        22210027
         MVC   0(L'IF,R12),IF                                           22220027
         MVC   L'IF(L'VAR,R12),VAR                                      22230027
         MVC   L'IF+L'VAR+1(L'OPER,R12),OPER                            22240027
         MVC   L'IF+L'VAR+L'OPER+2(L'VAR,R12),0(R7)                     22250027
         BAL   R9,CHKAMPRS         TRANSLATE & TO %%                    22260027
         LA    R7,L'EXP2(,R7)      POINT TO NEXT EXP2                   22270027
         BCT   R15,IF2LOOP                                              22280027
         LA    R12,80(,R12)        POINT TO NEXT CARD                   22290027
         BAL   R9,INSERT                                                22300027
         MVC   80(80,R12),0(R12)                                        22310027
         MVC   0(80,R12),=80C' '                                        22320027
         MVC   0(L'GOTO,R12),GOTO                                       22330027
         MVC   L'GOTO(L'IFCNT1,R12),IFCNT1      GOTO NNN1               22340027
*BC10338 MVC   L'GOTO+L'IFCNT1(2,R12),=C'XX'   EXCLUDE                  22350027
*BC10338 TM    FLAGS,ACTION              IS IT EXCLUDE?                 22360027
*BC10338 BO    IFEXCLD2                  YES                            22370027
         MVC   L'GOTO+L'IFCNT1(L'IFCNT2,R12),IFCNT2      GOTO NNN2      22380027
*BC10338IFEXCLD2 CVB   R15,EXP2CNT                           BC0083     22390027
         CVB   R15,EXP2CNT                           BC10338 BC0083     22400027
ELSEGOLP LA    R12,80(,R12)        POINT TO NEXT CARD        BC0083     22410027
         BAL   R9,INSERT                                                22420027
         MVC   80(80,R12),0(R12)                                        22430027
         MVC   0(80,R12),=80C' '                                        22440027
         MVC   0(L'ELSE,R12),ELSE                                       22450027
*        B     FALSGOTO                                         BC0083  22460027
         LA    R12,80(,R12)        POINT TO NEXT CARD           BC0083  22470027
         BAL   R9,INSERT                                        BC0083  22480027
         MVC   80(80,R12),0(R12)                                BC0083  22490027
         MVC   0(80,R12),=80C' '                                BC0083  22500027
         MVC   0(L'GOTO,R12),GOTO                               BC0083  22510027
         MVC   L'GOTO(L'IFCNT1,R12),IFCNT1      GOTO NNN1       BC0083  22520027
*BC10338 MVC   L'GOTO+L'IFCNT1(L'IFCNT2,R12),IFCNT2    EXCLUDE  BC0083  22530027
*BC10338 TM    FLAGS,ACTION              IS IT EXCLUDE?         BC0083  22540027
*BC10338 BO    IFEXCLD4                  YES                    BC0083  22550027
*BC10338 MVC   L'GOTO+L'IFCNT1(2,R12),=C'XX'   GOTO NNN-END     BC0083  22560027
         MVC   L'GOTO+L'IFCNT1(2,R12),=C'RU' GOTO NNN-ENDBC10338 BC0083 22570027
*BC10338IFEXCLD4 LA    R12,80(,R12)        POINT TO NEXT CARD   BC0083  22580027
         LA    R12,80(,R12)        POINT TO NEXT CARD    BC10338 BC0083 22590027
         BAL   R9,INSERT                                        BC0083  22600027
         MVC   80(80,R12),0(R12)                                BC0083  22610027
         MVC   0(80,R12),=80C' '                                BC0083  22620027
         MVC   0(L'ENDIF,R12),ENDIF                             BC0083  22630027
         BCT   R15,ELSEGOLP       DO ELSE GOTO LOOP             BC0083  22640027
         B     IFLABEL            POINT TO NEXT CARD            BC0083  22650027
TRTGLOBL TRT   0(*-*,R1),0(R14)  GLOBAL VARIABLE (% OR *)       BC10327 22660027
*BC10327 TRTGLOBL TRT   0(*-*,R1),GLOBAL  GLOBL VARIABLE (% OR *)       22670027
MVCVAR   MVC   VAR(*-*),0(R15)     VARIABLE NAME                        22680027
MVCOPER2 MVC   0(*-*,R7),0(R15)    R7 - ADDR OF EXP2 TABL               22690027
*                                                                       22703027
OPCEND   EQU   *                                                        22704027
         LA    R12,80(,R12)        POINT TO NEXT CARD                   22705027
         BAL   R9,INSERT                                                22706027
         MVC   80(80,R12),0(R12)                                        22707027
         MVC   0(80,R12),=80C' '                                        22708027
* CONT IF NO ACTION=NOSCAN                                      BC10268 22709027
         AHI   R1,4                OVER THE END KEYWORD         BC10268 22710027
         L     R14,=A(NONBLANK)                                 BC10758 22720027
*BC10758 TRT   0(60,R1),NONBLANK   R1 -> NEXT ITEM              BC10268 22730027
         TRT   0(60,R1),0(R14)     R1 -> NEXT ITEM              BC10758 22740027
         BZ    OPCENDLB            ONLY BLANKS - ADD LABEL      BC10268 22780027
         CLC   =C'ACTION=NOSCAN ',0(R1) IS IT END OF SCAN?      BC10268 22790027
         BNE   OPCENDLB            OTHER VALUES - ADD LABEL     BC10268 22800027
         MVC   0(L'RESON,R12),RESON                             BC10268 22810027
* INDICATE END                                                  BC10268 22820027
         NI    FLAGSCAN,X'FF'-$RESOFF MARK TO RESOLVE           BC10268 22830027
         B     OPCFIN                                           BC10268 22840027
OPCENDLB DS    0H                                               BC10268 22850027
         MVC   0(L'LABEL,R12),LABEL                                     22860027
         MVC   L'LABEL(L'IFCNT1,R12),IFCNT1                             22870027
         MVC   L'LABEL+L'IFCNT1(2,R12),=C'XX'   GOTO NNN-END            22880027
         AP    GOTOCNT1,=P'1'                                           22890027
         UNPK  IFCNT1,GOTOCNT1                                          22900027
         OI    IFCNT1+1,X'F0'                                           22910027
         ZAP   GOTOCNT2,=P'0'                                           22920027
*                                                                       22930027
OPCFIN   L     R9,SAVER9                                                22940027
         BR    R9                                                       22950027
*  PROCESS OPC/ESA RECOVER DIRECTIVE                             WC0001 22960027
OPCRECV  EQU   *             PROCESS OPC RECOVER STMT            WC0001 22970027
         LA    R1,9(,R1)          POINT PAST RECOVER             WC0001 22980027
         MVI   FLAGR,0            CLEAR RECV CONT FLGS          BC10758 22990027
OPCRECVC EQU   *                                                 WC0244 23000027
         L     R14,=A(NONBLANK)                                 BC10758 23010027
*BC10758 TRT   0(60,R1),NONBLANK  FIND KEYWORD            WC0001 WC0244 23020027
         TRT   0(60,R1),0(R14)    FIND KEYWORD            WC0001BC10758 23021027
         BZ    RECVPUT            NO PARAMETERS - DO DEFAULT ACTNWC0001 23025027
         ST    R1,CURRADDR  SV CURRADDR (IN CASE WE TAKE CONT BR)WC0244 23026027
         LA    R9,BALRRET    SET RETURN REG(R9) FOR SUBPARM CONT WC0244 23027027
         TM    FLAGR,$ADDAP  CHECK FOR CONTINUATION OF RECV PARAMWC0244 23028027
         BO    ADDAPMOR                                         WC0244  23029027
         TM    FLAGR,$ADDPR                                     WC0244  23030027
         BO    ADDPRMOR                                         WC0244  23040027
         TM    FLAGR,$DELST                                     WC0244  23050027
         BO    DELMORLP                                         WC0244  23060027
         TM    FLAGR,$JOBCO                                     WC0244  23070027
         BO    JOBMORLP                                         WC0244  23080027
**       TM    FLAGR,$STEPC                                     WC0244  23090027
         TM    FLAGR,$ERRST                                     WC0244  23100027
         BO    ERRMORLP                                         WC0244  23110027
**       TM    FLAGR,$RELSU                                     WC0244  23120027
OPCRECVL LR    R15,R1             SAVE CURRENT ADDR              WC0001 23130027
         L     R2,=A(EQUAL)                                      WC0237 23182027
         TRT   0(9,R1),0(R2)      FIND END OF KEYWORD            WC0237 23184027
*BC10758 BZ    OPCERR                                            WC0001 23188027
         BNZ   AFTERR3              FOUND '='               BC10758     23189027
*   FALSE CONTINUATION, FOLLOWED BY A 'RECOVER' CMD                     23210027
         CLC   =C'RECOVER',0(R1)                               BC10758  23211027
         BE    OPCRECV              YES                        BC10758  23212027
         B     OPCERR               NO                  BC10758         23213027
AFTERR3  EQU   *                                        BC10758         23215027
         ST    R1,CURRADDR       SAVE CURRENT ADDR              WC0001  23217027
         SR    R1,R15             LENGTH OF KEYWORD              WC0001 23218027
         BCTR  R1,0                                              WC0001 23219027
         MVC   RECVKEYW,=80C' '                                  WC0001 23220027
         EX    R1,RECVMVC                                        WC0001 23230027
         L     R2,=A(RECVTAB) TABL OF RECOVER KEYWORDS   WC0001 WC0225  23240027
RECVLOOP CLI   0(R2),X'FF'        END OF TABL                    WC0001 23250027
         BE    OPCERR             UNSUPPORTED KEYWORD            WC0001 23270027
         CLC   RECVKEYW,0(R2)                                    WC0001 23280027
         BE    RECVKEYF                                          WC0001 23290027
         LA    R2,RECVTABL(,R2)                                  WC0001 23300027
         B     RECVLOOP                                          WC0001 23310027
RECVMVC  MVC   RECVKEYW(*-*),0(R15)                              WC0001 23320027
*                                                                WC0001 23330027
RECVKEYF L     R1,CURRADDR         POINT TO =                    WC0001 23340027
         LA    R1,1(,R1)           POINT PAST '='                WC0001 23350027
         NI    FLAGS2,X'FF'-OPENPAR    RESET OPEN-PAREN FLAG     WC0001 23360027
         CLI   0(R1),C'('          IS PARAM ENCLOSED BY PARENS   WC0001 23370027
         BNE   NOPAREN                                           WC0001 23380027
         LA    R1,1(,R1)           POINT PAST '('                WC0001 23390027
         OI    FLAGS2,OPENPAR      SET OPEN-PAREN FLAG           WC0001 23400027
NOPAREN  L     R15,8(,R2)          GET PROPER RTN ADDRESS        WC0001 23410027
         BALR  R9,R15              AND BRANCH TO IT              WC0001 23420027
*                                                                WC0001 23430027
BALRRET  EQU   *        RETUN HERE ON SUB-PARAMETER CONTINUATN  WC0244  23440027
         NI    FLAGS2,X'FF'-NOADV  RESET                         WC0001 23469227
         L     R15,CURRADDR        FIND NEXT KEYWORD             WC0001 23469327
         LA    R1,1(,R15)          POINT PAST '='                WC0001 23469427
         LA    R15,71(,R12)        SET R15 TO END OF LINE        WC0001 23469527
         SR    R15,R1              NUMBER OF BYTES LEFT ON LINE  WC0001 23469627
         L     R2,=A(EQUAL)                                      WC0237 23469727
         EX    R15,NXKEYTRT        LOOK FOR =                    WC0001 23469827
         BZ    RECVCONT            NO MORE KEYWORDS ON THIS LINE WC0001 23490027
COMALOOP BCTR  R1,0               BACKUP TO FIND START OF KEYWORDWC0001 23500027
         CLI   0(R1),C','          LOOK FOR PRIOR COMMA          WC0001 23510027
         BNE   COMALOOP                                         WC0001  23520027
         LA    R1,1(,R1) FOUND COMMA - POINT TO START OF KEYWRD  WC0001 23530027
         B     OPCRECVL            LOOP TO PROCESS NEW KEYWRD    WC0001 23582027
*                                                                WC0001 23583027
RECVCONT EQU   *                                                WC10012 23584027
         L     R14,=A(BLANK)                                    WC10012 23600027
         EX    R15,ENDLINFD        FIND THE END OF THE LINE      WC0001 23610027
         BCTR  R1,0                POINT TO PRIOR NON-BLNK      WC0001  23620027
         NI    FLAGR,X'FF'-RECVMORE  RESET FLAG                 WC0244  23630027
         CLI   0(R1),C','          IS IT COMMA                   WC0001 23640027
         BNE   RECVPUT             NO - END OF RECOVER STMT      WC0001 23650027
         OI    FLAGR,RECVMORE     INDICATE CONTINUATION         WC0244  23660027
         B     OPCFIN                                            WC0001 23670027
RECVPUT  MVC   RECVJOBN,MEMBER      JOBNAME                      WC0001 23680027
         CLC   ERRSTEP(8*9),=80C' ' IS ERRSTEP(PROC,RANGE) BLNK WC0001  23705027
         BNE   PUT1                 NO - OK                      WC0001 23706027
         MVC   ERRSTEP,=C'ANYSTEP ' SET DEFAULT                  WC0001 23707027
         CLC   STPCODES(12*5),=80C' '  STEPCODES CODED?          WC0427 23708027
         BE    SKPEVERY             NO                           WC0427 23709027
         MVC   ERRSTEP,=C'+EVERY  '  YES- CHK AGAINST EVERY STEP WC0427 23710027
         B     PUT1                                              WC0427 23720027
SKPEVERY EQU   *                                                 WC0427 23730027
* FALL THRU HERE IF THERE IS NO STEPNAME (ERRSTEP) AND NO STEPCODES,    23740027
* (AND JOBCODES MAY BE PRESENT). THEN &RETCODE DETERMINES WHETHER THE   23750027
* ONPGM REFERS TO 'ANYSTEP' (RETCODE=HIGHEST) OR $LAST (RETCODE=LAST)   23760027
*WC10076 AIF   ('&RETCODE' NE 'LAST').NLAST                      WC0427 23770027
         CLC   =C'LAST',RETCODE                                 WC10076 23780027
         BNE   NLAST                                                    23790027
         MVC   ERRSTEP,=C'$LAST   ' NO- SET STEPNAME AS $LAST    WC0427 23800027
*WC10076 .NLAST   ANOP                                           WC0427 23810027
NLAST    DS    0H                                               WC10076 23820027
PUT1     CLC   JOBCODES(12*5),=80C' '   JOBCODES CODED?          WC0001 23830027
         BNE   PUT2                 YES                          WC0001 23840027
         CLC   STPCODES(12*5),=80C' '  STEPCODES CODED?          WC0001 23883027
         BNE   PUT2                 YES                          WC0001 23884027
         MVC   JOBCODES,=C'S*** '    SET ABEND DEFAULTS        WC0001   23885027
         MVC   JOBCODES+5(5),=C'U****'    SET ABEND DEFAULTS   WC0001   23886027
         MVC   JOBRANGE,=C'C0004'   SET DEFAULT                  WC0001 23887027
         MVC   JOBRANGE+5(5),=C'C4096'                     WC0001       23888027
PUT2     CLC   RESSTPNM,=80C' '     RESTART STEPNAME CODED?      WC0001 23889027
         BNE   PUTREC               YES                          WC0001 23890027
         MVC   RESSTPNM,=C'$FIRST  '  SET DEFAULT                WC0001 23900027
PUTREC   L     R1,=A(RECVEXT)                                    WC0225 23910027
         PUT   (R1),CTMOPROR                              WC0001 WC0225 23920027
         MVI   CTMOPROR,C' '        CLEAR NEW RECORD           WC0001   23930027
         MVC   CTMOPROR+1(256),CTMOPROR                        WC0001   23940027
         MVC   CTMOPROR+257(256),CTMOPROR                     BC10758   23950028
*BC10758 MVC   CTMOPROR+257(RECOVRLN-257),CTMOPROR           WC0001     23951028
         MVC   CTMOPROR+513(RECOVRLN-513),CTMOPROR            BC10758   23952028
         MVI   RECVFLAG,X'00'       INITIALIZE FLAG FLD          WC0001 23960027
         B     OPCFIN                                            WC0001 23970027
NXKEYTRT TRT   0(*-*,R1),0(R2)   R2=A(EQUAL)                     WC0237 23980027
*ENDLINFD TRT   0(*-*,R1),BLANK                         WC0001WC10012   23990027
ENDLINFD TRT   0(*-*,R1),0(R14)   FIND NEXT BLANK;R14=A(BLANK)  WC10012 24000027
*                                                                       24040027
CHKCONT  EQU   *        DO WE NEED TO PROCESS A CONTINATION?    WC0244  24050027
         CLI   0(R15),C' '       BLNK?                          WC0244  24070027
         BNE   OPCERR   NO - NOT A CONTINUATN - ERROR           WC0244  24080027
         CLC   =C'//*%OPC ',80(R12) NEXT LINE CONTAINS CONTIN?  WC0244  24100027
         BNE   OPCERR        NO                                 WC0244  24110027
         BR    R9            YES                                WC0244  24120027
***   RECOVER ERRSTEP=  ROUTINE   ********                       WC0001 24130027
RTNERRST LA    R7,ERRSTEP          R7=ERRSTEP NAME TABL          WC0001 24140027
         ZAP   RECVCNT,=P'0'       SET COUNT TO 0                WC0001 24150027
ERRMORLP NI    FLAGR,X'FF'-RECVMORE-$ERRST  RESET CONTIN FLAGS   WC0244 24160027
         LR    R15,R1              SAVE ADDR OF PARAM            WC0001 24170027
         MVI   SAVDELIM,0          CLEAR                         WC0001 24180027
         MVI   PARCOMA+C'-',C'-'   SET FOR DASH                  WC0001 24190027
         MVI   PARCOMA+C'.',C'.'   SET FOR DASH                  WC0001 24200027
         TRT   0(9,R1),PARCOMA     LOOK FOR ')'  ','  ' ' '-' '.'WC0001 24210027
         MVI   PARCOMA+C'-',X'00'  CLEAR                         WC0001 24250027
         MVI   PARCOMA+C'.',X'00'  CLEAR                         WC0001 24260027
         BZ    OPCERR              NO                            WC0001 24262027
         STC   R2,SAVDELIM         SAVE - OR . INDICATOR         WC0001 24263027
         CLI   0(R1),C'-'          WAS DELIM = '-'               WC0001 24264027
         BNE   ERRNDASH            NO                            WC0001 24265027
         SR    R1,R15        YES - GET LENGTH                    WC0001 24267027
         BZ    OPCERR              LENGTH=0 NG                   WC0237 24268027
         BCTR  R1,0                                              WC0001 24269027
         EX    R1,ERRMVC2A                                       WC0001 24270027
         OI    FLAGS2,NOADV        DONT ADVANCE ERRSTEP POINTER  WC0001 24280027
ERRCONT  LA    R1,2(R1,R15)        POINT PAST FIRST ERRSTEP+DLM  WC0001 24290027
         LR    R15,R1              SAVE ADDR                     WC0001 24300027
         TRT   0(9,R1),PARCOMA     LOOK FOR ')'  ','  ' '        WC0001 24320027
         BZ    OPCERR              NO END DELIMITER              WC0001 24360027
ERRSTP1  SR    R1,R15              GET LENGTH                    WC0001 24370027
         BNZ   LENOK1                                            WC0244 24380027
*BC10758 OI    FLAGR,RECVMORE+$ERRST                             WC0244 24390027
         OI    FLAGR,RECVMORE      CHECK FOR OTHER RECOV PARAMS BC10758 24400027
         B     CHKCONT         LENGTH=0 CHECK FOR CONTIN         WC0244 24410027
LENOK1   EQU   *                                                 WC0244 24420027
         BCTR  R1,0                                              WC0001 24430027
         CLI   SAVDELIM,C'-'       IS IT RANGE STEPNM            WC0001 24440027
         BE    ERRRNG2             NO                           WC0001  24450027
         CLI   SAVDELIM,C'.'       IS IT PROC  STEPNM            WC0001 24460027
         BNE   ERRSINGL            NO                           WC0001  24470027
         EX    R1,ERRMVC3B        YES - ITS PROC STEP NAME       WC0001 24480027
         B     ERRMORE                                           WC0001 24490027
ERRRNG2  EX    R1,ERRMVC2B              ITS RANG STEP NAME       WC0001 24500027
         B     ERRMORE                                           WC0001 24510027
ERRNDASH EQU   *                                                 WC0001 24520027
         CLI   0(R1),C'.'          WAS DELIM = '.'               WC0001 24530027
         BNE   ERRSTP1             NO                            WC0001 24540027
         SR    R1,R15        YES - GET LENGTH                    WC0001 24560027
         BZ    OPCERR              LENGTH=0 NG                   WC0237 24570027
         BCTR  R1,0                                              WC0001 24580027
         EX    R1,ERRMVC3A                                       WC0001 24590027
         OI    FLAGS2,NOADV        DONT ADVANCE ERRSTEP R7 PTR   WC0001 24600027
         B     ERRCONT                                           WC0001 24610027
*                                                                WC0001 24620027
ERRSINGL AP    RECVCNT,=P'1'                                     WC0001 24630027
         CLC   RECVCNT,=P'5'                                     WC0001 24650027
         BH    OPCERR                                            WC0001 24660027
         EX    R1,ERRSTMV1         SIMPLE ERRSTEP NM             WC0001 24670027
         CLI   0(R7),C'*'          ERROR   ON ANYSTEP?         BC10354X 24680027
         BNE   ERRMORE             NO                          BC10354X 24690027
         MVC   0(8,R7),=C'ANYSTEP '   YES                      BC10354X 24700027
ERRMORE  EQU   *                                                 WC0001 24710027
         CLM   R2,1,=C','          END?                          WC0001 24711027
         BNER  R9                  YES - ITS EITHER ' ' OR ')'   WC0001 24712027
         TM    FLAGS2,OPENPAR      WAS OPEN-PAREN CODED          WC0001 24713027
         BNOR  R9                  NO - COMMA MEANS END OF ERRST WC0001 24714027
         LA    R1,2(R1,R15)        POINT PAST (FIRST) ERRSTEP    WC0001 24715027
         TM    FLAGS2,NOADV     ADVANCE POINTER IN R7 TBL?       WC0001 24716027
         BO    ERRSTXIT                                          WC0001 24717027
         LA    R7,L'ERRSTEP(,R7)  MORE ERRSTEPS                 WC0001  24718027
         B     ERRMORLP            LOOP FOR MORE                 WC0001 24719027
ERRSTXIT NI    FLAGS2,X'FF'-NOADV                                WC0001 24720027
         B     ERRMORLP                                          WC0001 24730027
ERRSTMV1 MVC   0(*-*,R7),0(R15)      SIMPLE ERRSTEP           WC0001    24740027
ERRMVC2A MVC   ERRSTPRG(*-*),0(R15)  RANGE STEP MOVE             WC0001 24750027
ERRMVC2B MVC   ERRSTPRG+8(*-*),0(R15)  RANGE STEP MOVE           WC0001 24760027
ERRMVC3A MVC   ERRSTPPR(*-*),0(R15)  PROC STEP NAME MOVE         WC0001 24770027
ERRMVC3B MVC   ERRSTPPR+8(*-*),0(R15)  PROC STEP NAME MOVE       WC0001 24780027
*                                                                       24790027
***   RECOVER DELSTEP=  ROUTINE   ********                       WC0001 24800027
RTNDELST OI    FLAGS2,DELSTEPF     SET DELSTEP FLAG              WC0001 24810027
         ZAP   RECVCNT,=P'0'       SET COUNT TO 0                WC0001 24820027
         LA    R7,DELSTPNM         R7=DELSTEP NAME TABL          WC0001 24830027
DELMORLP NI    FLAGR,X'FF'-RECVMORE-$DELST  RESET CONTIN FLAGS   WC0244 24840027
         LR    R15,R1              SAVE ADDR OF PARAM            WC0001 24850027
         MVI   SAVDELIM,0          CLEAR                         WC0001 24860027
         MVI   PARCOMA+C'-',C'-'   SET FOR DASH                  WC0001 24870027
         TRT   0(9,R1),PARCOMA     LOOK FOR ')'  ','  ' ' '-'    WC0001 24880027
         MVI   PARCOMA+C'-',X'00'  CLEAR                         WC0001 24920027
         BZ    OPCERR              NO - ERROR                    WC0001 24940027
         STC   R2,SAVDELIM         SAVE DLM INDICATOR            WC0001 24950027
         CLI   0(R1),C'-'          WAS DELIM = '-'               WC0001 24960027
         BNE   DELSTP1             NO                            WC0001 24970027
         SR    R1,R15         YES- GET LENGTH                    WC0001 24990027
         BZ    OPCERR              LENGTH=0 NG                   WC0237 25000027
         BCTR  R1,0                                              WC0001 25010027
         EX    R1,DELSTMV2                                       WC0001 25020027
         OI    FLAGS2,NOADV       DONT ADVANCE DELSTEP POINTER   WC0001 25030027
         LA    R1,2(R1,R15)        POINT PAST FIRST DELSTEP      WC0001 25040027
         LR    R15,R1              SAVE ADDR                     WC0001 25050027
         TRT   0(9,R1),PARCOMA     LOOK FOR ')'  ','  ' '        WC0001 25070027
         BZ    OPCERR              NO END DELIMITER              WC0001 25092027
DELSTP1  SR    R1,R15              GET LENGTH                    WC0001 25093027
         BNZ   LENOK2                                            WC0244 25094027
         OI    FLAGR,RECVMORE+$DELST                             WC0244 25095027
         B     CHKCONT         LENGTH=0 CHECK FOR CONTIN         WC0244 25096027
LENOK2   EQU   *                                                 WC0244 25097027
         BCTR  R1,0                                              WC0001 25098027
         CLI   SAVDELIM,C'-'       IS IT RANGE STEPNM            WC0001 25099027
         BNE   NODELRNG            NO                            WC0001 25100027
         EX    R1,DELSTMV3        YES - ITS 2ND RANG STEP NAME   WC0001 25110027
         B     DELMORE                                           WC0001 25120027
NODELRNG AP    RECVCNT,=P'1'                                     WC0001 25130027
         CLC   RECVCNT,=P'5'                                     WC0001 25150027
         BH    OPCERR                                            WC0001 25160027
         EX    R1,DELSTMV1         SIMPLE STEP NAME              WC0001 25170027
DELMORE  CLM   R2,1,=C','          END?                          WC0001 25180027
         BNE   DELADDTB            YES - ITS EITHER ' ' OR ')'   WC0001 25190027
         TM    FLAGS2,OPENPAR      WAS OPEN-PAREN CODED          WC0001 25200027
         BNO   DELADDTB            NO - COMMA MEANS END          WC0001 25210027
         LA    R1,2(R1,R15)        POINT PAST FIRST DELSTEP      WC0001 25220027
         TM    FLAGS2,NOADV       DONT ADVANCE DELSTEP POINTER?  WC0001 25230027
         BO    DELSTXIT              YES                         WC0001 25240027
         LA    R7,L'DELSTPNM(,R7)  MORE DELSTEPS                 WC0001 25250027
         B     DELMORLP            LOOP FOR MORE                 WC0001 25260027
DELSTXIT NI    FLAGS2,X'FF'-NOADV                                WC0001 25270027
         B     DELMORLP                                          WC0001 25280027
*                                                                WC0001 25290027
DELADDTB CLI   DELRANGE,C' '       ANY RANGE                     WC0001 25300027
         BE    SKPDELRG            NO                            WC0001 25310027
         MVC   DELSTPTR(16),DELRANGE YES - SAVE THE DEL RANGE    WC0001 25320027
SKPDELRG LA    R15,5               ADD NEW DELETE STEPS          WC0001 25330027
         LA    R1,10               TOTAL DEL STEPS IN MEMBR     WC0001  25340027
         L     R2,=A(DELSTPTB)                                   WC0237 25350027
         LA    R7,DELSTPNM                                       WC0001 25360027
DELADLP1 CLI   0(R7),C' '        NO MORE DELSTEPS TO ADD       WC0001   25370027
         BER   R9                                                WC0001 25380027
DELADLP2 CLI   0(R2),C' '        ROOM TO ADD?                  WC0001   25390027
         BE    DELADSTP            YES                           WC0001 25400027
         LA    R2,8(,R2)           NEXT BUCKET                   WC0001 25410027
         BCT   R1,DELADLP2                                       WC0001 25420027
         B     OPCERR              TOO MANY DELSTEPS             WC0001 25440027
DELADSTP BCTR  R1,0                                              WC0001 25450027
         LTR   R1,R1                                             WC0001 25470027
         BM    OPCERR                                     WC0001 WC0244 25480027
         MVC   0(8,R2),0(R7)       FILL TABL              WC0001 WC0244 25490027
         LA    R7,8(,R7)                                         WC0001 25500027
         LA    R2,8(,R2)                                         WC0001 25510027
         BCT   R15,DELADLP1                                      WC0001 25520027
         BR    R9                                                WC0001 25530027
DELSTMV1 MVC   0(*-*,R7),0(R15)                                  WC0001 25540027
DELSTMV2 MVC   DELRANGE(*-*),0(R15)  RANGE STEP MOVE             WC0001 25550027
DELSTMV3 MVC   DELRANGE+8(*-*),0(R15)  RANGE STEP MOVE (2ND)     WC0001 25560027
*                                                                       25570027
***   RECOVER RESSTEP=  ROUTINE   ********                       WC0001 25580027
RTNRESST EQU   *                                                 WC0001 25590027
         MVC   RESSTPNM,=C'$FIRST  '                             WC0001 25600027
         CLI   0(R1),C'*'          RESTART AT FIRST STEP         WC0001 25610027
         BER   R9                                                WC0001 25620027
         MVC   RESSTPNM,=C'$EXERR  '                             WC0001 25630027
         CLI   0(R1),C'%'          RESTART AT FAILING STEP       WC0001 25640027
         BER   R9                                                WC0001 25650027
         MVC   RESSTPNM,=80C' '    CLEAR                         WC0001 25660027
         LR    R15,R1              SAVE ADDR OF PARAM            WC0001 25670027
         MVI   SAVDELIM,0          CLEAR                         WC0001 25680027
*WC10012 L     R2,=A(PERIOD)                                    WC0237  25690027
         L     R2,=A(TRTPER)                             WC0237 WC10012 25700027
         TRT   0(9,R1),0(R2)       LOOK FOR '.'                  WC0237 25710027
         BZ    RESST1              NO       -SIMPLE RESSTEP      WC0001 25750027
         STC   R2,SAVDELIM    YES- SAVE '.' INDICATOR            WC0001 25760027
         SR    R1,R15              GET LENGTH                    WC0001 25780027
         BZ    OPCERR              LENGTH=0 NG                   WC0237 25790027
         BCTR  R1,0                                              WC0001 25800027
         EX    R1,RESSTMV1                                       WC0001 25810027
         LA    R1,2(R1,R15)        POINT PAST FIRST RESSTEP      WC0001 25820027
RESST1   LR    R15,R1              SAVE ADDR                     WC0001 25830027
         TRT   0(9,R1),PARCOMA R1->LOOK FOR  ','  ' '        WC0001     25850027
         BZ    OPCERR              NO END DELIMITER              WC0001 25854027
         SR    R1,R15              GET LENGTH                    WC0001 25856027
         BZ    OPCERR              LENGTH=0 NG                   WC0237 25857027
         BCTR  R1,0                                              WC0001 25858027
         CLI   SAVDELIM,C'.'       IS IT PROC  STEPNM            WC0001 25859027
         BNE   NORESPRC            NO                            WC0001 25860027
         EX    R1,RESSTMV2        YES - ITS PROC STEP NAME       WC0001 25870027
         BR    R9                                                WC0001 25880027
NORESPRC EQU   *                                                 WC0001 25890027
         EX    R1,RESSTMV1         SIMPLE STEP NAME              WC0001 25900027
         BR    R9                                                WC0001 25910027
RESSTMV1 MVC   RESSTPNM(*-*),0(R15)                             WC0001  25920027
RESSTMV2 MVC   RESSTPRC(*-*),0(R15)  PROC STEP MOVE              WC0001 25930027
*                                                                       25940027
***   RECOVER ALTJOB=   ROUTINE   ********                    BC10433   25950027
RTNALTJO EQU   *                                              BC10433   25960027
         MVC   ALTJOB,=80C' '    CLEAR                        BC10433   25970027
         LR    R15,R1              SAVE ADDR OF PARAM         BC10433   25971027
         TRT   0(9,R1),PARCOMA     LOOK FOR ')'  ','  ' '     BC10433   25973027
         BZ    OPCERR              NO END DELIMITER           BC10433   25977027
         SR    R1,R15              GET LENGTH                 BC10433   25979027
         BZ    OPCERR              LENGTH=0 NG                BC10433   25980027
         BCTR  R1,0                                           BC10433   25981027
         EX    R1,ALTJOBMV         RERUNMEM                   BC10433   25981127
         OI    RECVFLAG,$NOIFRER   PREVENT DO=IFRERUN         BC10433   25981227
         BR    R9                                             BC10433   25981327
ALTJOBMV MVC   ALTJOB(*-*),0(R15)                             BC10433   25981427
*                                                                       25981527
***   RECOVER RESTART=  ROUTINE   ********                       WC0001 25981627
RTNRESTA EQU   *                                               WC0001   25981727
         CLI   0(R1),C'Y'        RESTART=Y                     WC0001   25981827
         BER   R9                 YES - DEFAULT IS YES           WC0001 25981927
         OI    RECVFLAG,RESTART  SET NO                          WC0001 25982027
         BR    R9                                                WC0001 25983027
***   RECOVER TIME=     ROUTINE   ********                       WC0001 25984027
RTNTIME  CLC   0(9,R1),=C'0000-2400'                             WC0001 25985027
         BNER  R9                 YES - NEED CONFIRMATION        WC0001 25986027
         OI    RECVFLAG,NOCONFRM  SET NO CONFIRMATION            WC0001 25987027
         BR    R9                                                WC0001 25988027
***   RECOVER ADDAPPL=/RELSUCC= RTN ******                       WC0001 25989027
RTNADDAP LA    R7,ADDAPPL          R7=ADDAPPL NAME TABL          WC0001 25990027
         ZAP   MAXAPPL,=P'5'     SET MAX CNTR                   BC10758 25991028
RTNRELSX ZAP   RECVCNT,=P'0'                              WC0001 WC0237 26000027
ADDAPMOR NI    FLAGR,X'FF'-RECVMORE-$ADDAP  RESET CONTIN FLAGS   WC0244 26010027
         LR    R15,R1              SAVE ADDR OF PARAM            WC0001 26020027
         TRT   0(17,R1),PARCOMA    LOOK FOR ')'  ','  ' '        WC0237 26040027
         BZ    OPCERR              NO END DELIMITER              WC0001 26080027
         SR    R1,R15              GET LENGTH                    WC0001 26090027
         BNZ   LENOK3                                            WC0244 26100027
         OI    FLAGR,RECVMORE+$ADDAP                             WC0244 26110027
         B     CHKCONT         LENGTH=0 CHECK FOR CONTIN         WC0244 26120027
LENOK3   EQU   *                                                 WC0244 26130027
         BCTR  R1,0                                              WC0001 26140027
         AP    RECVCNT,=P'1'                                     WC0001 26150027
*BC10354 CLC   RECVCNT,=P'5'                                     WC0001 26160027
*BC10758 CP    RECVCNT,=P'5'                          WC0001  BC10354   26180028
         CP    RECVCNT,MAXAPPL                        BC10354  BC10758  26181028
         BH    OPCERR                                            WC0001 26190027
         MVC   WORKAPPL,=80C' '    CLEAR APPLID WORK AREA       WC0237  26200027
         EX    R1,ADDAPMV1         MOVE APPL NAME                WC0001 26210027
         ST    R1,SAVER1           SAVE R1                      WC0237  26220027
         TM    FLAGS2,$RELSUCC     SKIP OBTAINING SHORT NAME     WC0467 26230027
         BO    MVRELSUC            AND USE FULL 16-BYTES         WC0467 26240027
         L     R1,CHGSTART         GET OLD/NEW APPLID TBL       WC0237  26250027
FOLDAPPL C     R1,CHGEND           END OF TBL?                  WC0237  26260027
         BNL   OPCERR              YES - OLD APPL NOT FOUND     WC0237  26280027
         CLC   WORKAPPL,0(R1)      FIND THE OLD APPL            WC0237  26290027
         BE    FNEWAPPL            FOUND IT                     WC0237  26300027
         LA    R1,32(,R1)          TRY NEXT ENTRY               BC10327 26310027
         B     FOLDAPPL            LOOP                         WC0237  26320027
FNEWAPPL MVC   0(8,R7),16(R1)      KEEP NEW APPL IN TBL         WC0237  26330027
         LA    R7,L'ADDAPPL(,R7)   FOR NEXT APPL NAME         WC0467    26340027
FNEWAPL2 EQU   *                                              WC0467    26350027
         L     R1,SAVER1           RESTORE R1                   WC0237  26360027
         CLM   R2,1,=C','          END?                          WC0001 26370027
         BNE   RELSUCX             YES (BLNK OR ')')            BC10354 26380027
         TM    FLAGS2,OPENPAR      WAS OPEN-PAREN CODED          WC0001 26390027
         BNO   RELSUCX             NO                           BC10354 26400027
*WC0467  LA    R7,L'ADDAPPL(,R7)  MORE APPL NAMES               WC0001  26410027
         LA    R1,2(R1,R15)        POINT PAST FIRST APPL         WC0001 26420027
         B     ADDAPMOR            LOOP FOR MORE                 WC0001 26430027
MVRELSUC MVC   0(16,R7),WORKAPPL   KEEP ORIG APPL IN TBL         WC0467 26440027
         LA    R7,L'RELSUCC(,R7)  MORE                           WC0467 26450027
*BC10354 NI    FLAGS2,X'FF'-$RELSUCC    RESET                    WC0467 26460027
         B     FNEWAPL2                                          WC0467 26470027
RELSUCX  EQU   *                                               BC10354  26480027
         NI    FLAGS2,X'FF'-$RELSUCC    RESET                  BC10354  26490027
         BR    R9                                              BC10354  26500027
*ADDAPMV1 MVC   0(*-*,R7),0(R15)                          WC0001 WC0237 26510027
ADDAPMV1 MVC   WORKAPPL(*-*),0(R15)                              WC0237 26520027
*                                                                       26530027
***   RECOVER RELSUCC=  ROUTINE   ********                       WC0237 26540027
RTNRELSU LA    R7,RELSUCC          R7=RELSUCC NAME TABL          WC0237 26550027
         OI    FLAGS2,$RELSUCC     USE FULL APPL NAME (16 CHAR)  WC0467 26560027
         ZAP   MAXAPPL,=P'25'    SET MAX CNTR                   BC10758 26561028
         B     RTNRELSX            SAME RTN AS RTNAPPL           WC0237 26570027
***   RECOVER ADDPROC=  ROUTINE   ********                       WC0237 26580027
RTNADDPR LA    R7,ADDPRCNM         R7=ADDPRCNM TABL              WC0237 26590027
         ZAP   RECVCNT,=P'0'                                     WC0237 26600027
         OI    FLAGS0,ADDPWAIT     SET FLAG TO ADD AUTO-EDIT     WC0237 26610027
ADDPRMOR NI    FLAGR,X'FF'-RECVMORE-$ADDPR  RESET CONTIN FLAGS   WC0244 26620027
         LR    R15,R1              SAVE ADDR OF PARAM            WC0237 26630027
         TRT   0(9,R1),PARCOMA     LOOK FOR ')'  ','  ' '        WC0237 26650027
         BZ    OPCERR              NO END DELIMITER              WC0237 26690027
         SR    R1,R15              GET LENGTH                    WC0237 26700027
         BNZ   LENOK4                                            WC0244 26710027
         OI    FLAGR,RECVMORE+$ADDPR                             WC0244 26720027
         B     CHKCONT         LENGTH=0 CHECK FOR CONTIN         WC0244 26730027
LENOK4   EQU   *                                                 WC0244 26740027
         BCTR  R1,0                                              WC0237 26750027
         AP    RECVCNT,=P'1'                                     WC0237 26760027
         CLC   RECVCNT,=P'5'                                     WC0237 26780028
         BH    OPCERR                                            WC0237 26790027
         EX    R1,ADDPRMV1         MOVE PROC NAME                WC0237 26800027
         CLM   R2,1,=C','          END?                          WC0237 26810027
         BNE   PRCADDTB            YES                           WC0237 26820027
         TM    FLAGS2,OPENPAR      WAS OPEN-PAREN CODED          WC0237 26830027
         BNO   PRCADDTB            NO                            WC0237 26840027
         LA    R7,L'ADDPRCNM(,R7)  MORE PROCNAMES                WC0237 26850027
         LA    R1,2(R1,R15)        POINT PAST FIRST PROCNAME     WC0237 26860027
         B     ADDPRMOR            LOOP FOR MORE                 WC0237 26870027
ADDPRMV1 MVC   0(*-*,R7),0(R15)                                  WC0237 26880027
*                                                               WC02307 26890027
PRCADDTB LA    R15,5               ADD NEW PROCNAMES             WC0237 26900027
         LA    R1,10               TOTAL PROCNAMES IN MEMBR     WC0237  26910027
         L     R2,=A(PROCNMTB)                                   WC0237 26920027
         LA    R7,ADDPRCNM                                       WC0237 26930027
PRCADLP1 CLI   0(R7),C' '        NO MORE PROCNAMES TO ADD       WC0237  26940027
         BER   R9                                                WC0237 26950027
PRCADLP2 CLI   0(R2),C' '        ROOM TO ADD?                  WC0237   26960027
         BE    PROCADD             YES                           WC0237 26970027
         CLC   0(8,R7),0(R2)     PROCNM ALREADY EXISTS IN LIST? BC10758 26971027
         BE    PRCADLP4             YES                         BC10758 26972027
         LA    R2,8(,R2)           NEXT BUCKET                   WC0237 26973027
         BCT   R1,PRCADLP2                                       WC0237 26974027
         B     OPCERR              TOO MANY PROCNAMES            WC0237 26976027
PROCADD  BCTR  R1,0                                              WC0237 26977027
         LTR   R1,R1                                             WC0237 26979027
         BM    OPCERR              EXCEEDED MAX           WC0237 WC0244 26980027
         MVC   0(8,R2),0(R7)       FILL TABL              WC0237 WC0244 26990027
         LA    R2,8(,R2)                                        BC10758 27000027
PRCADLP3 EQU   *                                                BC10758 27010027
         LA    R7,8(,R7)                                         WC0237 27020027
*BC10758 LA    R2,8(,R2)                                         WC0237 27030027
         BCT   R15,PRCADLP1                                      WC0237 27040027
         BR    R9                                                WC0237 27050027
PRCADLP4 EQU   *                                                BC10758 27060027
         L     R2,=A(PROCNMTB)    RESET TO START OF LIST        BC10758 27070027
         B     PRCADLP3       ADV TO NXT PROC CANDIDATE TO ADD  BC10758 27080027
***   RECOVER JOBCODE=  ROUTINE   ********                       WC0001 27090027
RTNJOBCO EQU   *                                                        27100027
         LA    R7,JOBCODES         R7=JOBCODES TABL          WC0001     27110027
STPCDBAL ZAP   RECVCNT,=P'0'       SET COUNT TO 0                WC0001 27120027
JOBMORLP NI    FLAGR,X'FF'-RECVMORE-$JOBCO  RESET CONTIN FLAGS   WC0244 27130027
         LR    R15,R1              SAVE ADDR OF PARAM            WC0001 27140027
         MVI   SAVDELIM,0          CLEAR                         WC0001 27150027
         MVI   PARCOMA+C'-',C'-'   ADD IN DASH                   WC0001 27160027
         TRT   0(5,R1),PARCOMA     LOOK FOR '-' ')' ',' ' '      WC0001 27170027
         MVI   PARCOMA+C'-',X'00'  CLEAR                         WC0001 27180027
         BZ    OPCERR              NO                            WC0001 27182027
         STC   R2,SAVDELIM         SAVE DLM INDICATOR            WC0001 27183027
         CLI   0(R1),C'-'          HIT DASH FIRST               WC0001  27184027
         BNE   JOBCD1              NO    - SINGLE JOBCODE        WC0001 27185027
         SR    R1,R15         YES- GET LENGTH                    WC0001 27187027
         BZ    OPCERR              LENGTH=0 NG                   WC0237 27188027
         BCTR  R1,0                                              WC0001 27189027
         EX    R1,JOBCDPK          PACK THE RC                   WC0001 27190027
         SP    WORK,=P'1'          SUBTRACT 1                    WC0001 27200027
         UNPK  JOBRANGE,WORK       UNPACK IT                     WC0001 27210027
         OI    JOBRANGE+4,X'F0'    FIX SIGN                      WC0001 27220027
         MVI   JOBRANGE,C'C'       CNNNN                         WC0001 27230027
         LA    R1,2(R1,R15)        POINT PAST DASH               WC0001 27240027
         LR    R15,R1              R15 - POINT TO 2ND RANGE      WC0001 27250027
         TRT   0(5,R1),PARCOMA     LOOK FOR  ')' ',' ' '      WC0001    27270027
         BZ    OPCERR                                            WC0001 27280027
JOBCD1   SR    R1,R15              GET LENGTH                    WC0001 27290027
         BNZ   LENOK5                                            WC0244 27300027
         OI    FLAGR,RECVMORE+$JOBCO                             WC0244 27310027
         B     CHKCONT         LENGTH=0 CHECK FOR CONTIN         WC0244 27320027
LENOK5   EQU   *                                                 WC0244 27330027
         BCTR  R1,0                                              WC0001 27340027
         CLI   SAVDELIM,C'-'       IS IT RANGE JOBCODE           WC0001 27350027
         STC   R2,SAVDELIM         SAVE NEW DELIM                WC0001 27360027
         BNE   NOJOBRNG            NO                            WC0001 27370027
         EX    R1,JOBCDPK          PACK THE RC                   WC0001 27380027
         AP    WORK,=P'1'          ADD 1                         WC0001 27390027
         UNPK  JOBRANGE+5(5),WORK       UNPACK IT              WC0001   27400027
         OI    JOBRANGE+9,X'F0'         FIX SIGN               WC0001   27410027
         MVI   JOBRANGE+5,C'C'          CNNNN                  WC0001   27420027
         OI    FLAGS2,NOADV       DONT ADVANCE JOBCODE RNG POINTRWC0001 27430027
         B     JOBMORE                                           WC0001 27440027
NOJOBRNG AP    RECVCNT,=P'1'                                     WC0001 27450027
         CLC   RECVCNT,=P'10'                                    WC0001 27470027
         BH    OPCERR                                            WC0001 27480027
         EX    R1,JOBCDMV1         SINGLE JOB CODE - MOVE IT IN  WC0001 27490027
         STH   R1,SAVLENG         LENGTH OF JOBCODE             WC0001  27500027
         L     R2,=A(NUMTRT)                                    WC0225  27510027
         EX    R1,JOBCDTRT        IS IT NUMERIC?                WC0001  27520027
*BC0515  BNZ   NOTRC               NO                            WC0001 27530027
         LH    R1,SAVLENG                                        WC0001 27540027
         BNZ   NOTRC               NO                           BC0515  27550027
         EX    R1,JOBCDPK     YES- PACK THE RC                   WC0001 27560027
         UNPK  0(5,R7),WORK       UNPACK IT                   WC0001    27570027
         OI    4(R7),X'F0'         FIX SIGN                   WC0001    27580027
         MVI   0(R7),C'C'          CNNNN                      WC0001    27590027
         B     JOBMORE             CONTINUE LOOKING              WC0001 27600027
* FILL CODE OUT TO FULL 4 BYTES                                  WC0001 27610027
*BC10327 NOTRC    TRT   0(4,R7),GLOBAL   IS IT A GENERIC JOBCODE WC0001 27620027
NOTRC    DS    0H                                               BC10327 27630027
         L     R1,=A(GLOBAL)       IS IT A GENERIC JOBCODE      BC10327 27640027
         TRT   0(4,R7),0(R1)       IS IT A GENERIC JOBCODE      BC10327 27650027
         BZ    NOTGENER            NO                            WC0001 27660027
GENCDLP  EQU   *                                                BC10293 27670027
         CLC   =C'* ',0(R7)        JOBCODE=* --> S***,U****     BC10293 27680027
         BE    GENCD2              YES                          BC10293 27690027
         CLI   3(R7),C' '          IS 4TH BYTE BLNK             WC0001  27700027
         BNE   CHKUXXXX            NO - LEAVE ASIS               WC0001 27710027
         MVC   3(1,R7),2(R7)       YES- MOVE 3RD BYTE TO 4TH     WC0001 27720027
         CLI   2(R7),C'*'          DID WE MOVE *                 WC0001 27730027
         BE    CHKUXXXX            YES - DONE                    WC0001 27740027
         MVC   2(1,R7),1(R7)       NO - MOVE 2ND BYTE TO 3RD     WC0001 27750027
         CLI   1(R7),C'*'          DID WE MOVE *                 WC0001 27760027
         BE    GENCDLP             YES                           WC0001 27770027
         MVC   1(1,R7),0(R7)       NO - MOVE 1ST BYTE TO 2ND     WC0001 27780027
         B     GENCDLP                                           WC0001 27790027
GENCD2   MVC   0(4,R7),=C'S***'                                 BC10293 27800027
         AHI   R7,L'JOBCODES       POINT TO NEXT SLOT           BC10293 27810027
         MVC   0(5,R7),=C'U****'                                BC10293 27820027
         B     JOBMOREX                                         BC10293 27830027
*                                                                WC0001 27840027
CHKUXXXX CLI   0(R7),C'U'          YES- IS IT USER ABEND CODE    WC0001 27850027
         BNE   GENCONT           NO ('S' SYS ABEND COPIED AS-IS) WC0001 27860027
         CLC   1(3,R7),=C'***'     IS IT U***                    WC0001 27880027
         BNE   OPCERR              NO - NOT SUPPORTED            WC0001 27890027
ADDASTSK MVI   4(R7),C'*'          YES- CHANGE TO U****          WC0001 27900027
         B     JOBMOREX                                          WC0001 27910027
*                                                                WC0001 27920027
GENCONT  CLI   0(R7),C'*'          IS IT *XXX ?                  WC0001 27930027
         BNE   JOBMOREX            NO- * NOT IN FIRST POSITION   WC0001 27940027
         CLC   1(3,R7),=C'***' YES-IT IS **** ?                  WC0001 27950027
         BE    ADDASTSK        YES-CHANGE TO *****               WC0001 27960027
         L     R1,=A(GLOBAL)       IS IT A GENERIC JOBCODE      BC10327 27970027
         TRT   1(3,R7),0(R1)       NO  - ANY OTHER *'S          BC10327 27980027
*BC10327 TRT   1(3,R7),GLOBAL      NO  - ANY OTHER *'S           WC0001 27990027
         BNZ   JOBMOREX            YES        - DONT TREAT AS U  WC0001 28000027
         AP    RECVCNT,=P'1'       NO- CREATE A UXXXX            WC0001 28010027
         CLC   RECVCNT,=P'10'                                    WC0001 28030027
         BH    OPCERR                                            WC0001 28040027
         MVC   L'JOBCODES(4,R7),0(R7) CREATE 2ND CODE FOR U TYPE WC0001 28050027
         LA    R7,L'JOBCODES(,R7)                                WC0001 28060027
         B     TRANSU                                            WC0001 28070027
NOTGENER CLI   0(R7),C'U'          IS IT UXXX                    WC0001 28080027
         BNE   NOTU                NO                            WC0001 28090027
TRANSU   L     R1,=A(HEXTRANS)                                   BC0101 28100027
         TR    1(3,R7),0(R1)     Y-CONVERT C'Y' TO X'YY'  WC0001 BC0101 28110027
         PACK  WORK,1(3,R7)       PACK IN 8-BYTE WORK AREA       WC0001 28120027
         MVO   WORK+5(3),WORK+5(2) SHIFT OUT LAST H-BYTE (SIGN)  WC0001 28130027
         L     R1,WORK+4           PUT INTO R1                   WC0001 28140027
         CVD   R1,WORK             CONVERT TO PACK FORMAT        WC0001 28150027
         UNPK  1(4,R7),WORK+5(3)   CONVERT TO CHARACTER          WC0001 28160027
         OI    4(R7),X'F0'         ZONED SIGN                    WC0001 28170027
         MVI   0(R7),C'U'          MAKE UXXXX                    WC0001 28180027
         B     JOBMOREX                                          WC0001 28190027
NOTU     EQU   *                                                WC10018 28200027
         L     R2,=A(CODESTBL) TABL OF TWS ERROR CODES         BC10370  28210027
CODLOOP  CLI   0(R2),X'FF'        END OF TABL                  BC10370  28220027
         BE    CHKCASE            CHECK FOR CASE CODES         BC10370  28230027
         CLC   0(L'JOBCODES,R7),0(R2)  FIND TWS CODE IN TBL    BC10370  28240027
         BNE   CODLOOP2                                        BC10370  28250027
         MVC   0(L'JOBCODES,R7),L'JOBCODES(R2) XLAT TO CTM CODEBC10370  28260027
         B     JOBMOREX                                        BC10370  28270027
CODLOOP2 AHI   R2,L'CODESTBL                                   BC10370  28280027
         B     CODLOOP                                         BC10370  28290027
*                                                                WC0001 28300027
CHKCASE  L     R2,=A(CASETBL)                            WC0001 BC0101  28310027
         LA    R1,20              NUMBER OF CASECODE ENTRIES    WC0001  28320027
JOBCASCD CLI   0(R2),C' '         EMPTY ENTRY                    WC0001 28330027
         BE    JOBMOREX            DIDNT FIND CASE CODE TRANSLAT WC0001 28340027
         CLC   0(4,R7),0(R2)       FOUND CASE CODE ENTRY ?       WC0001 28350027
         BE    JOBCASFD            YES                           WC0001 28360027
         LA    R2,11*5(,R2)     NO-POINT TO NEXT CASE REC IN TBL WC0001 28370027
         BCT   R1,JOBCASCD                                      WC0001  28380027
         B     JOBMOREX           DIDNT FIND CASE CODE TRANS     WC0001 28390027
*                                                                WC0001 28400027
JOBCASFD LA    R1,10              MAX 10 CODE ENTRIES           WC0001  28410027
JOBCASLP LA    R2,5(,R2)                                         WC0001 28420027
         CLI   0(R2),C' '          ANY MORE CODE ENTRIES         WC0001 28430027
         BE    JOBMOREX            NO                            WC0001 28440027
         MVC   0(5,R7),0(R2)       YES                           WC0001 28450027
         LA    R7,5(,R7)                                         WC0001 28460027
         OI    FLAGS2,NOADV       DONT ADVANCE JOBCODE POINTER   WC0001 28470027
         AP    RECVCNT,=P'1'                                     WC0001 28480027
         CLC   RECVCNT,=P'10'                                    WC0001 28500027
         BH    OPCERR                                            WC0001 28510027
         BCT   R1,JOBCASLP                                       WC0001 28520027
JOBMOREX LH    R1,SAVLENG          LEN OF JOBCODE                WC0001 28530027
JOBMORE  EQU   *                                                        28540027
         CLI   SAVDELIM,C','       END?                          WC0001 28550027
         BNER  R9                  YES                           WC0001 28560027
         TM    FLAGS2,OPENPAR      WAS OPEN-PAREN CODED          WC0001 28570027
         BNOR  R9                  NO                            WC0001 28580027
         LA    R1,2(R1,R15)        POINT PAST FIRST JOBCODE      WC0001 28590027
         TM    FLAGS2,NOADV        SHOULD WE ADVANCE POINTER     WC0001 28600027
         BO    JOBCDXIT            NO                            WC0001 28610027
         LA    R7,L'JOBCODES(,R7)  YES -MORE JOBCODES            WC0001 28620027
         B     JOBMORLP            LOOP FOR MORE                 WC0001 28630027
JOBCDXIT NI    FLAGS2,X'FF'-NOADV  RESET                         WC0001 28640027
         B     JOBMORLP                                          WC0001 28650027
JOBCDMV1 MVC   0(*-*,R7),0(R15)                                  WC0001 28660027
JOBCDPK  PACK  WORK,0(*-*,R15)       RANGE PACK                  WC0001 28670027
JOBCDTRT TRT   0(*-*,R15),0(R2)   R2=A(NUMTRT) VALIDATE NUMERICS WC0001 28680027
***   RECOVER STEPCODE= ROUTINE   ********                       WC0001 28690027
RTNSTEPC LA    R7,STPCODES             R7=STPCODES TABL          WC0001 28700027
         MVC   STPRANGE(10),JOBRANGE                             WC0001 28710027
         ST    R9,SAVER9X                                        WC0001 28720027
         BAL   R9,STPCDBAL         DO STPCODES RTN               WC0001 28730027
         L     R9,SAVER9X                                        WC0001 28740027
         XC    JOBRANGE(10),STPRANGE   SWITCH JOB AND STEPRANGE  WC0001 28750027
         XC    STPRANGE(10),JOBRANGE                             WC0001 28760027
         XC    JOBRANGE(10),STPRANGE                             WC0001 28770027
         BR    R9                                                WC0001 28780027
***   RECOVER ERROR RTN           ********                       WC0001 28790027
RTNERROR EQU   *      PUT OUT ERROR OR JUST IGNORE???            WC0001 28800027
*.NOTESA6 ANOP                                           WC0024  WC0237 28810027
         BR    R9                                                WC0001 28820027
*        INSERT CARD TO MEMBR                                           28830027
*BC10273 INSERT   ST    R15,SAVER15X        R2, R15 ARE SAVED           28840027
INSERT   DS    0H                                               BC10273 28850027
         LARL  R3,SAVER15I LOCATION FOR SAVING R15 WITHOUT USINGBC10273 28860027
*BC10273 ST    R15,SAVER15X        R2, R15 ARE SAVED                    28870027
         ST    R15,0(R3)           R2, R15 ARE SAVED            BC10273 28880027
         LARL  R3,SAVER2I  LOCATION FOR SAVING R15 WITHOUT USINGBC10273 28890027
*BC10273 ST    R2,SAVER2                                      WC0237    28900027
         ST    R2,0(R3)                                         BC10273 28910027
         LR    R3,R11              MOVE REMAINING LINES COUNTER         28920027
         BCTR  R3,0                MINUS 1                              28930027
         LA    R2,80(,R12)         FROM ADDRES                          28940027
         LTR   R3,R3               Q. NEED SHIFT?                       28950027
         JZ    INSSKIP             A. NO - SKIP                         28960027
         MHI   R3,80               TIMES LINE LEN                       28970027
         LR    R15,R3                                                   28980027
         LARL  R3,AWORK            WORK ARE ADDRESS             BC10273 28990027
*BC10273 L     R14,AWORK            TO ADDRESS                          29000027
         L     R14,0(R3)            TO ADDRESS                  BC10273 29010027
         LR    R3,R15                                           BC10273 29020027
MVCLE1   MVCLE R14,R2,0             SHIFT                     WC10026   29030027
         JO    MVCLE1                                           BC10273 29040027
         LA    R2,160(,R12)        TO ADDRES                            29050027
         LR    R3,R11              MOVE REMAINING LINES COUNTER         29060027
         BCTR  R3,0                MINUS 1                              29070027
         MHI   R3,80               TIMES LINE LEN               BC10273 29080027
         LR    R15,R3                                                   29090027
         LARL  R3,AWORK            WORK ARE ADDRESS             BC10273 29100027
*BC10273 L     R14,AWORK            FROM ADDRESS                        29110027
         L     R14,0(R3)            FROM ADDRESS                BC10273 29120027
         LR    R3,R15                                           BC10273 29130027
MVCLE2   MVCLE R2,R14,0             SHIFT                     WC10026   29140027
         JO    MVCLE2                                           BC10273 29150027
INSSKIP  equ   *                                                        29160027
         MVC   80(80,R12),=80C' '   CLEAR CARD                 BC10447  29170027
         TM    FLAGS0,SYSINPDS  ARE WE PROCESSING SYSIN MEMBR BC10360   29180027
         BO    ADDSYSIN            YES                         BC10360  29190027
         LARL  R15,LINE#   LOCATION OF LINE COUNTER             BC10273 29200027
*BC10273 L     R3,LINE#                                                 29210027
         L     R3,0(R15)                                        BC10273 29220027
         LA    R3,1(,R3)                                                29230027
*BC10273 ST    R3,LINE#                                                 29240027
         ST    R3,0(R15)                                        BC10273 29250027
*        LA    R11,1(,R11)     INCREASE REMAINING COUNT <== DONT NEED   29260027
INSCONT  EQU   *                                               BC10360  29270027
         LARL  R3,SAVER2I  LOCATION FOR SAVING R15 WITHOUT USINGBC10273 29280027
*BC10273 L     R2,SAVER2                                      WC0237    29290027
         L     R2,0(R3)                                         BC10273 29300027
         LARL  R3,SAVER15I LOCATION FOR SAVING R15 WITHOUT USINGBC10273 29310027
*BC10273 L     R15,SAVER15X                                             29320027
         L     R15,0(R3)                                        BC10273 29330027
         BR    R9                                                       29340027
ADDSYSIN AP    DELCNT,=P'-1'  SUBTRACT 1 TO DELETE CNT FOR SYSINBC10360 29350027
         B     INSCONT                                          BC10360 29360027
SAVER15I DS    F                                                BC10273 29370027
SAVER2I  DS    F                                                BC10273 29380027
*    DELETE CARD - REGS R0,R1,R2,R3 ARE USED AS WORK                    29390027
DELETE   LR    R3,R11              MOVE REMAINING LINES COUNTER         29400027
         BCTR  R3,0                MINUS 1                              29410027
         LA    R2,80(,R12)         FROM ADDRES                          29420027
         LTR   R3,R3               Q. NEED SHIFT?                       29430027
         BZ    DELSKIP             A. NO - SKIP                         29440027
         MH    R3,=H'80'           TIMES LINE LEN                       29450027
         LR    R1,R3                                                    29460027
         L     R0,AWORK            TO WORK AREA                         29470027
*WC10026 MVCL  R0,R2               SHIFT                                29480027
MVCLE3   MVCLE R0,R2,0             SHIFT                      WC10026   29490027
         BC    1,MVCLE3                                       WC10026   29500027
         LR    R3,R11              MOVE REMAINING LINES COUNTER         29510027
         BCTR  R3,0                MINUS 1                              29520027
         MH    R3,=H'80'           TIMES LINE LEN                       29530027
         LA    R2,0(,R12)          TO ADDRES                            29540027
         LR    R1,R3                                                    29550027
         L     R0,AWORK            FROM ADDRESS                         29560027
*WC10026 MVCL  R2,R0               SHIFT                                29570027
MVCLE4   MVCLE R2,R0,0             SHIFT                      WC10026   29580027
         BC    1,MVCLE4                                       WC10026   29590027
DELSKIP  EQU   *                                                        29600027
         TM    FLAGS0,SYSINPDS     ARE WE PROCESSING SYSIN MEMBRWC0225  29610027
         BO    DELSYSIN            YES                           WC0225 29620027
         L     R3,LINE#                                                 29630027
         BCTR  R3,0                                                     29640027
         ST    R3,LINE#                                                 29650027
DELCONT  SH    R12,=H'80'          POINT TO PREV LINE            WC0225 29660027
         BR    R9                                                       29670027
DELSYSIN AP    DELCNT,=P'1'        ADD 1 TO DELETE CNT FOR SYSIN WC0225 29680027
         B     DELCONT                                           WC0225 29690027
*                                                                       29700027
CHKAMPRS EQU   *                                                        29710027
*WC10076 AIF   ('&VER' NE 'E').NOTESA7                           WC0001 29720027
         CLI   VER,C'E'                                         WC10076 29730027
         BNE   NOTESA7                                          WC10076 29740027
*WC10076 AIF   ('&AUTSCAN' EQ 'Y').SKPSCN1                       WC0082 29750027
         CLI   AUTSCAN,C'Y'                                     WC10076 29760027
         BE    SKPSCN1                                          WC10076 29770027
         TM    FLAGS0,SCAN         IS SCAN FLAG ON               WC0082 29780027
         BNOR  R9                  NO                            WC0082 29790027
SKPSCN1  DS    0H                                               WC10076 29800027
         ST    R15,SAVER15                                              29810027
         ST    R12,CHKAMP12        PASS VALUE TO FUNCTION       BC10273 29820027
         ST    R11,CHKAMP11        PASS VALUE TO FUNCTION       BC10273 29830027
         LA    R1,CHKAMPPR                                      BC10273 29840027
         L     R15,=A(CHKAMPBG)                                 BC10273 29850027
         BASR  R14,R15                                          BC10273 29860027
         LTR   R15,R15             ANY ERROR DETECTED ?         BC10273 29870027
         JZ    CHKAMPRT            NO - RET                     BC10273 29880027
         ST    R9,SAVER9    SET FOR PROPER RETURN AFTER ERR     BC10273 29900027
         J     OPCERR              YES - NOTIFY                 BC10273 29910027
CHKAMPRT DS    0H                                               BC10273 29920027
         L     R12,CHKAMP12        TAKE UPDATED VALUE FROM FUNC BC10273 29930027
         L     R11,CHKAMP11        TAKE UPDATED VALUE FROM FUNC BC10273 29940027
         L     R15,SAVER15                                      BC10273 29950027
NOTESA7  DS    0H                                               BC10273 29960027
         BR    R9                                               BC10273 29970027
         AGO   .AFCHKAMP                                        BC10273 29980027
.BFCHKAMP ANOP                                                  BC10273 29990027
         DROP ,                                                 BC10273 29991099
*-------------------------------------------------------------- BC10918 30000034
CHKAMPBG DS    0F                                               BC10918 30002099
*BC10918 SUBXSET                                                BC10918 30010099
         BEGIN CHKAMPBG                                         BC10273 30020099
         L     R8,=A(CTMO15WS)                                  BC10918 30021099
         LAY   R5,4096(,R8)                                     BC10918 30021199
         USING CTMO15WS,R8,R5                                   BC10918 30021299
*BC10918 L     R8,=A(VARTAB)     ADDRESSABILITY ON DATA AREA    BC10273 30030063
*BC10918 USING VARTAB,R8                                        BC10273 30040063
         ST    R1,CHKAMPPA                                      BC10273 30050027
         L     R12,0(,R1)     LINE PTR FROM PARAMETR            BC10273 30060027
         L     R11,4(,R1)     LINE CNT FROM PARAMETR            BC10273 30070027
         NI    FLAGS1,X'FF'-$VARXST-$FNLSQZ  CLEAR      BC10351 BC10370 30080027
         LR    R1,R12             POINT TO START OF LINE                30090027
         MVC   N,=C'0000000'     INIT INDEX FOR SET STMT        BC10091 30100027
         MVI   VARNDX,C'0'       INIT VAR NDX WHEN SQZING LINE BC10450  30101027
         MVC   LINELEN,=H'70'  SET LINELENG mO 70 FOR JCL TYPE   BC0283 30102099
         CLC   =C'//',0(R1)    IS THIS A JCL LINE?               BC0283 30103027
         BE    SETLINEL        YES                               BC0283 30104027
         MVC   LINELEN,=H'78'  SET LINELENG TO 78 FOR DATA TYPE  BC0283 30105027
SETLINEL LH    R15,LINELEN                                       BC0283 30106027
*AMPRSLP  EX    R15,TRTAMPRS    0(*-*,R1),AMPERSND. FIND &, %, ?BC10091 30107027
*BC10370 NI    FLAGS1,X'FF'-$VARXST          CLEAR              BC10351 30108027
AMPRSLP  EQU   *                                                BC10091 30109027
         L     R2,=A(AMPERSND)                                  BC10091 30110027
         EX    R15,TRTAMPRS    0(*-*,R1),0(R2)     FIND &, %, ? BC10091 30120027
         BZ    AMPEND              NO MORE VARIABLES                    30130027
*WC10049 TRT   1(1,R1),AMPERSND       IS &, %, ? DOUBLED                30140027
*WC10049 BNZ   NOCONVRT             TEMP FILE OR ALREADY CONVERTED      30150027
*WC10049 CLI   1(R1),C' '           &,%,? FOLLOWED BY BLANK?    WC10012 30160027
*WC10049 BE    NOCONVRT             YES - ITS NOT A VARIABLE    WC10012 30170027
*WC10049 CLI   1(R1),C''''          &,%,? FOLLOWED BY QUOTE?    BC10061 30180027
*WC10049 BE    NOCONVRT             YES - ITS NOT A VARIABLE    BC10061 30190027
         L     R15,=A(DELIM)       VAR-SYMBOL FOLLOWED BY DELIM?WC10049 30200027
         TRT   1(1,R1),0(R15)  E.G. &&-TEMPFILE, '1%', '? 'ETC. WC10049 30210027
         BNZ   NOCONVRT            YES - ITS NOT A VARIABLE     WC10049 30220027
*BC10351 OI    FLAGS1,$VARXST   INDIC THERES A VARIABLE ON LINE BC10084 30230027
         CLI   0(R1),C'?'          ?-VARIABLE ?                 WC10049 30240027
         BE    CHKQMARK           SEE IF WE CAN SUPPORT THIS '?'BC10351 30250027
QMARKOK  EQU   *                                                BC10351 30260027
         OI    FLAGS1,$VARXST  INDIC THERES VAR ON LINE BC10084 BC10351 30270027
*  IF MEMBR CONTAINS IN-STREAM PROC MUST CHECK IF THE VARS ARE          30280027
*  STANDARD JCL VARS (WHICH SHOULD NOT BE CONVERTED) OR OPC VARS        30290027
*  TO CHECK: USE THE VARIABLE TABL LIST PRODUCED IN 51PRC TO SEE IF     30300027
*            VARNAME DEFINED THERE. IF YES, DONT CONVERT IT.            30310027
         ST    R1,SAVER1           SAVE POS OF VAR (INCLUDES &) BC10064 30320027
* CHECK IF VAR WAS DEFINED BY A // SET PREVIOUSLY IN JCL        BC10268 30330027
         L     R2,ERROR      LOAD THE ERROR MESSAGE DCB ADDRESS BC10893 30331028
         L     R15,=A(CHKJSET)                                  BC10268 30340027
         BASR  R14,R15                                          BC10268 30350027
         LTR   R15,R15             Q. HAVE WE FOUND VAR IN TABLEBC10268 30360027
         JZ    NOCONVRT            A. YES - DON'T CONVERT       BC10268 30370027
         L     R15,=A(DELIM)       FIND DELIM OF VAR IN JCL LINEBC10064 30380027
         TRT   1(9,R1),0(R15)                                   BC10064 30390027
         BZ    NOCONVRT         VAR NAME MORE THAN 8; NOT A VAR BC10115 30400027
         L     R15,SAVER1          POS OF VAR                   BC10064 30410027
         SR    R1,R15              LEN OF VAR IN JCL            BC10064 30420027
         BCTR  R1,0                SUB 1 FOR INITIAL & OR %     BC10064 30430027
         ST    R1,SAVLENV        SAVE VAR NAME LEN (W/O &)     BC10450  30440027
         LR    R0,R1               SAVE VAR LENG IN R0          BC10064 30450027
         L     R2,CTM5VART    GET ADDR OF VAR TBL LIST ADDR     BC10064 30460027
VARTBLLP CLI   0(R2),C' '          NO MORE ENTRIES              BC10064 30470027
         BE    AMPRSLP0            PROCESS IT AS AN OPC VAR     BC10064 30480027
         ST    R2,SAVER2           SAVE R2 ACROSS TRT           BC10064 30490027
         L     R15,=A(EQUAL)    FIND '=' (VARNAME DELIM IN TBL) BC10064 30500027
         TRT   0(9,R2),0(R15)                                   BC10064 30510027
         L     R2,SAVER2           RESTORE                      BC10064 30520027
         SR    R1,R2               GET LENG OF VAR IN TBL       BC10064 30530027
         CR    R0,R1               IS JCL AND TBL VAR SAME LEN  BC10064 30540027
         BNE   VARTBLNX            NOT SAME VAR - KEEP LOOKING  BC10064 30550027
         L     R15,SAVER1          POINT TO JCL VAR (INCLUDES &)BC10064 30560027
         BCTR  R1,0                -1 FOR EX INSTRUCTN          BC10064 30570027
         EX    R1,CLCVAR       CLC 0(*-*,R2),1(R15)             BC10064 30580027
         L     R1,SAVER1     1ST RESTORE R1 POINTR BEFORE BRANCHBC10064 30590027
         BE    NOCONVRT      FOUND IN VAR TBL - NOT AN OPC VAR! BC10064 30600027
VARTBLNX EQU   *        FIND NEXT VAR IN TBL LIST               BC10064 30610027
         L     R15,=A(EQFFTAB)    LOOK FOR VARNAME=VALFF DELIM  BC10064 30620027
*BC10447 TRT   0(80,R2),0(R15)                                  BC10064 30630027
         TRT   0(255,R2),0(R15)                       BC10064 BC10447   30640027
         LA    R2,1(,R1)          POINT TO NEXT VAR SLOT        BC10064 30650027
         B     VARTBLLP                                         BC10064 30660027
*VARNXT   LA    R2,9(,R2)      NEXT ENTRY IN VARNMTBL  BC10084 BC10091  30670027
*VARNXT   LA    R2,17(,R2)      NEXT ENTRY IN VARNMTBL  BC10091 BC10093 30680027
VARNXT   LA    R2,25(,R2)      NEXT ENTRY IN VARNMTBL           BC10093 30690027
         B     VARTBLP2       KEEP SEARCHING                    BC10084 30700027
CLCVAR   CLC   0(*-*,R2),1(R15)       SAME VAR NAME?            BC10064 30710027
AMPRSLP0 L     R1,SAVER1        RESTORE POS OF VAR     BC10064          30720027
         CHI   R0,6           IGNORE SYSTEM SYMBOLIC &SYSUID   BC10119  30730027
         BNE   NSYSUID        ITS NOT SYSUID                   BC10119  30740027
         CLC   =C'SYSUID',1(R1)                                BC10119  30750027
         BE    NOCONVRT       IGNORE  SYSUID                   BC10119  30760027
NSYSUID  EQU   *                                               BC10119  30770027
* A STRING PRECEDED BY A '%' CAN BE AN OPC VAR OR A CLIST/REXX NAME     30780027
* CHECK THE SYSPROC CONCATENATN W/ IOAMEM TO SEE IF ITS A CLIST NAME.   30790027
* IF YES - SKIP THE VARIABLE PROCESSING.                                30800027
         CLI   0(R1),C'%'       IS IT A PERCENT VAR?            BC10093 30810027
         BNE   NOTCLIST         NO                              BC10093 30820027
         CLC   =C'//',0(R12)   ON A JCL LINE (NOT A DATA LINE)?BC10450  30830027
         BE    NOTCLIST       YES-CANT BE A CLIST              BC10450  30840027
         LR    R2,R0            YES - GET ITS LENG (SEE ABOVE)  BC10093 30850027
         BCTR  R2,0             -1                              BC10093 30860027
         MVC   WORK,=80C' '     CLEAR WORK AREA                 BC10093 30870027
MLA#206  DS    0H                                              BC10918  30871046
         MVC   WORK(*-*),1(R1)                                  BC10093 30880027
*BC10918 EX    R2,*-6                                           BC10093 30890046
         EX    R2,MLA#206                                       BC10918 30891046
         LA    R2,VARLINE                                       BC10093 30900027
* BECAUSE OF BUG IN DIRALL FUNCTION (THE MEMBER= PARM IS IGNORED), IT   30910027
* WAS DECIDED TO USE THE GETMEM INSTEAD                                 30920027
*BC10450 IOAMEM DIRALL,    CHK IF IT EXISTS IN SYSPROC CONCAT  BC10093  30930027
         IOAMEM GETMEM,    CHK IF IT EXISTS IN SYSPROC BC10093 BC10450 *30940027
               IOAMEMA=ACTMMEM,                                BC10093 *30950027
               MCTADDR=MCTADDR,                                BC10093 *30960027
               DDNAME==CL8'SYSPROC',                           BC10093 *30970027
               MEMBER=WORK,                                    BC10093 *30980027
               BUFFADR=(R2),                                   BC10093 *30990027
               RECNUM=1                                        BC10093  31000027
         ST    R15,SAVER15X                                    BC10093  31010027
*****    IOAMEM FINISH,      CLEANUP                           BC10093 *31020027
               IOAMEMA=ACTMMEM,                                BC10093 *31030027
               MCTADDR=MCTADDR,                                BC10093 *31040027
               DDNAME==CL8'SYSPROC'                            BC10093  31050027
         L     R1,SAVER1     1ST RESTORE R1 POINTR BEFORE BRANCHBC10093 31060027
         ICM   R15,15,SAVER15X                                 BC10093  31070027
         BZ    NOCONVRT     ITS A CLIST NAME, NOT A VAR        BC10093  31080027
         CLC   IMRSN,=H'24'  R15=8;  BUFFER FILLED BY CLIST    BC10093  31090027
         BE    NOCONVRT     ITS A CLIST NAME, NOT A VAR        BC10093  31100027
*BC10450 CLC   IMRSN,=H'0'   EMPTY DIRECTORY (RC=8, RS=0)?     BC10093  31110027
         CLC   IMRSN,=H'20'  CLIST MEMBER DOESNT EXIST?BC10093 BC10450  31120027
         BE    NOTCLIS0 YES -NOT A CLIST NAME; MUST BE OPC VAR BC10115  31130027
         ST    R10,SAVER10                                     BC10093  31140027
         BAL   R10,IOAMEERA  NO-  SERIOUS ERR - WRITE ERRMSG   BC10093  31150027
         L     R10,SAVER10                                     BC10093  31160027
NOTCLIS0 EQU   *                                               BC10115  31170027
         L     R1,SAVER1         RESTORE R1 IN CASE OF ERR ABV BC10093  31180027
*  TO PREVENT FALSE MATCHES WHEN A CLIST NAME STARTS W/ '%'             31190027
*  CHECK IF VAR IS DEFINED IN AN OPC JCLVAR TABL                        31200027
* BC10091 - ALL VARIABLES (EVEN &) ARE NOW CHECKED IN JCLVAR TABL       31210027
*  VARNMTBL- VARNAM(8) + LEN (1) + INDEPEND-VAR (8) + TBLNM (8)         31220027
NOTCLIST EQU   *                                               BC10093  31230027
         L     R2,=A(TABLE)      LIST OF 'TABLE'S              BC10093  31240027
         CLI   0(R2),C' '        UNDER AN OPC 'TABL'?         BC10093   31250027
         BE    NVARTBL           NO TABLES SPECIFIED - SKIP    BC10093  31260027
         L     R2,VARNMTBL    TBL OF VARNM/LENG FROM OP018     BC10084  31270027
VARTBLP2 EQU   *                                               BC10084  31280027
         L     R1,SAVER1  RESTORE R1 POINTR IN CASE OF BRANCH  BC10084  31290027
         CLI   0(R2),C' '         NO MORE ENTRIES              BC10084  31300027
*BC10091 BE    NOCONVRT         END OF TABL  - NOT AN OPC VAR   BC10084 31310027
         BE    NVARTBL     NOT IN JCLVAR TBL - SKIP   BC10084  BC10091  31320027
*   CHECK IF THE TABL THIS VAR IS IN, MATCHES ANY TABL NAMES            31330027
*   FROM THE LIST OF TABL IN THE OPC '//*% OPC TABLE NAME=(...)' STMT   31340027
         L     R15,=A(TABLE)     LIST OF 'TABLE'S              BC10093  31350027
         LA    R14,8             MAX OF 8 TABL NAMES          BC10093   31360027
VTLP2A   CLI   0(R15),C' '       UNDER AN OPC 'TABL'?         BC10093   31370027
         BE    VARNXT            NO - TRY NXT VAR IN VARNMTBL  BC10093  31380027
         CLC   0(8,R15),17(R2)   TABL-NAMES MATCH?            BC10093   31390027
         BE    VTLP3         YES-CONTINUE                      BC10093  31400027
         LA    R15,L'TABLE(,R15)       NEXT TABL-NAME IN LIST BC10093   31410027
         BCT   R14,VTLP2A        RETRY                         BC10093  31420027
         B     VARNXT            NO MATCH                      BC10093  31430027
VTLP3    EQU   *                                               BC10093  31440027
         SR    R1,R1                                            BC10084 31450027
         IC    R1,8(R2)     R1=LEN OF VAR IN JCLVAR REPORT      BC10084 31460027
         CR    R0,R1        R0=LEN OF VAR IN JCL                BC10084 31470027
         BNE   VARNXT           CHECK NEXT ENTRY                BC10084 31480027
         L     R15,SAVER1          POINT TO JCL VAR (INCLUDES &)BC10084 31490027
         BCTR  R1,0                -1 FOR EX INSTRUCTN          BC10084 31500027
         EX    R1,CLCVAR       CLC 0(*-*,R2),1(R15)             BC10084 31510027
         BNE   VARNXT       NO- CHECK NEXT ENTRY                BC10084 31520027
         L     R1,SAVER1  RESTOR R1 TO VAR POS FOR ADDINCLB ADJ BC10093 31530027
         BAL   R14,ADDINCLB    YES-(CHANGES FLAG TURNED ON HERE)BC10091 31540027
         OI    FLAGS,CHANGES                                    BC10091 31550027
*  CHECK IF THE VARIABLE IS DEFINED IN THE JCLVAR TABL WITH INDEPEND    31560027
*  VAR VALUES. IF YES WE MUST APPEND THE INDEPEND VAR TO THE VAR NAME   31570027
*  AS FOLLOWS: %%VARNAME_%%INDEPEND-VAR (E.G. %%VAR1_%%ODD)             31580027
*  THE INDEPENDENT VAR WILL BE RESOLVED FROM THE 'SYSTEM' MEMBR         31590027
*  THE FOLLOWING LINE WILL BE INSERTED TO THE JCL MEMBR                 31600027
*    %%SET %%N...N = %%VARNAME_%%INDEPEND-VAR                           31610027
*   WHERE VAR N...N IS LENG MINUS 1 OF THE ORIGINAL VAR                 31620027
*  AND THE VARIABL ITSELF REPLACED WITH %%N (N=0-9) IN JCL LINE         31630027
*BC10093 L     R1,SAVER1  RESTOR R1 TO VAR POS IN CASE OF BRNCHBC10091  31640027
         CLI   9(R2),C' '     IS THERE INDEP VAR VALUE?        BC10091  31650027
         BE    AMPRSLP2       NO                               BC10091  31660027
         IC    R1,N               UP THE INDEX FOR SET STMT    BC10091  31670027
         AHI   R1,1      IN CASE OF MULTIPLE VARS ON LINE      BC10091  31680027
         STC   R1,N                                            BC10091  31690027
         MVC   N+1(L'N-1),N   CHANG 0...0 TO 1...1 ETC         BC10091  31700027
         ST    R9,SAVER9X     SAVE                             BC10091  31710027
*BC10273 BAL   R9,INSERT                                                31720027
         LARL  R9,INSERT                                        BC10273 31730027
         BALR  R9,R9                                            BC10273 31740027
         L     R9,SAVER9X     RESTORE                          BC10091  31750027
         MVC   80(80,R12),0(R12)                               BC10091  31760027
         MVC   0(80,R12),=80C' '                               BC10091  31770027
         MVC   0(20,R12),=C'%%SET %%0       = %%'              BC10091  31780027
         SR    R15,R15                                         BC10091  31790027
         IC    R15,8(R2)             GET VAR-NAME LEN          BC10091  31800027
** REDUCE THE LENG BY 2 FOR: 1. THE %%0...0 NAME SHOULD BE 1 LESS       31810027
** THAN THE &VAR NAME (BECAUSE OF EXTRA '%') AND                        31820027
** 2. 'EX' INSTRUCTION                                                  31830027
         MVC   8(1,R12),N   MOVE 1-DIGIT 'N' IN CASE LEN=1     BC10091  31840027
         AHI   R15,-2                                          BC10091  31850027
         BM    VARLEN1A     IF ORIG LEN=1 MUST DO LINE SHIFTS  BC10091  31860027
MLA#207  DS    0H                                              BC10918  31861046
         MVC   8(*-*,R12),N                                    BC10091  31870027
*BC10918 EX    R15,*-6                                         BC10091  31880046
         EX    R15,MLA#207                                     BC10918  31881046
VARLEN1A MVC   20(8,R12),0(R2)         VAR-NAME                BC10091  31890027
         MVC   WORK,9(R2)       SAVE INDEPEND VAR-NAME         BC10091  31900027
         L     R2,=A(BLANK)     FIND BLNK  AFTER VAR-NAME      BC10091  31910027
         TRT   20(9,R12),0(R2)  FIND BLNK  AFTER VAR-NAME      BC10091  31920027
         MVC   0(3,R1),=C'_%%'                                 BC10091  31930027
         MVC   3(8,R1),WORK       INDEPEND VAR NAME            BC10091  31940027
         LA    R12,80(,R12)    GET PAST INSERTED LINE          BC10091  31950027
         L     R1,SAVER1    YES- RESTORE R1 POINTR - POS OF VAR BC10084 31960027
         LA    R1,80(,R1)   ADJUST AFTER INSERT- POS OF VAR    BC10091  31970027
         ST    R1,SAVER1    SAVE NEW POS                       BC10091  31980027
         MVC   1(1,R1),N    IN CASE VAR LEN IS 1               BC10091  31990027
         LTR   R15,R15          WAS ORIGINAL LEN=1 (R15 MINUS) BC10091  32000027
         BM    AMPRSLP2         YES - DO LINE SHIFTING         BC10091  32010027
MLA#208  DS    0H                                              BC10918  32011046
         MVC   2(*-*,R1),N  OVERLAY VARNAME W/ 0...0 (AFTR %%) BC10091  32020027
*BC10918 EX    R15,*-6                                         BC10091  32030046
         EX    R15,MLA#208                                     BC10918  32031046
         B     AMPRSLP3        SKIP LINE SHIFTING              BC10091  32040027
NVARTBL  EQU   *               NOT FOUND IN JCLVAR TBL        BC10091   32050027
*BC10093 CLI   0(R1),C'%'       IS IT A PERCENT VAR?            BC10091 32060027
*BC10093 BE    NOCONVRT         YES - NOT REALLY AN OPC VAR     BC10091 32070027
*AMPRSLP1 EQU   *          NO - REGULAR &-VAR NOT IN JCLVAR TBL BC10091 32080027
         BAL   R14,ADDINCLB        (CHANGES FLAG TURNED ON HERE)        32090027
         OI    FLAGS,CHANGES                                  BC0282    32100027
*  SQZ OF EMBEDDED BLANKS BEFORE THE 1ST VARIABLE OCCURRANCE            32110027
*  ONLY DONE WHEN SHIFTEND=N AND ITS A JCL LINE (//)                    32120027
*!!POINTER TO THE VAR (R1) MUST BE ADJUSTED IF THE BLNK-SQZ             32130027
*  HAPPENS ON THE LINE BEFORE THE POSITION OF THE VAR                   32140027
FNLSQZ   EQU   *       SQZ EMBEDDED BLNKS                       BC10370 32150027
         CLI   SHIFTEND,C'N'     ALLOW ANYWHERE SHIFTING        BC10370 32160027
         BNE   AFTSQZ              NO EMBEDED SQZING            BC10370 32170027
         CLC   =C'//',0(R12)     ONLY FOR JCL (NON-DATA) LINES  BC10370 32180027
         BNE   AFTSQZ              NO EMBEDED SQZING            BC10370 32190027
         TM    FLAGS1,$FNLSQZ     FINAL BLNK SQZ ALREADY DONE? BC10370  32200027
         BO    AFTSQZ             YES                          BC10370  32210027
         OI    FLAGS1,$FNLSQZ  MARK FINAL BLNK SQZ ALREADY DONE BC10370 32220027
         LA    R2,2(,R12)        START SQZ FROM COL 3           BC10370 32230027
* SET R15 TO LEN OF TAIL TO MOVE (-1 FOR EX),                           32240027
         LA    R15,67            ONLY UP TO COL71               BC10370 32250027
         CLI   71(R12),C',' COLUMN 72 CONTAINS CONTINUATN ','? BC10450  32251027
*BC10918 BNE   *+8             NO                              BC10450  32252031
         BNE   MLA#108         NO                              BC10918  32252131
         AHI   R15,1           YES - SQUEEZE IT DOWN ALSO      BC10450  32253027
MLA#108  DS    0H                                              BC10918  32253131
FNLSQZ2  CLC   =C'  ',0(R2)      CAN WE SQZ AT LEAST 1 BLNK?    BC10370 32254027
         BE    FNLSQZ3           YES                            BC10370 32255027
         AHI   R2,1                NO - ADJ LINE PTR AND LENG   BC10370 32256027
FNLSQZ2B BCTR  R15,0                                            BC10370 32257027
         LTR   R15,R15                   MORE TO SQZ            BC10370 32258027
         BNZ   FNLSQZ2                   YES                    BC10370 32259027
         B     AFTSQZ     READY TO PROCESS FIRST VAR            BC10370 32260027
FNLSQZ3  EQU   *               SQZ OUT 1 BLNK; CLEAR VACATED POSBC10370 32270027
         EX    R15,MVFNLSQZ     MVC   0(*-*,R2),1(R2)           BC10370 32280027
         CR    R1,R2    IS SHIFT HAPPENING BEFORE OCCUR OF VAR? BC10370 32290027
*BC10918 BL    *+6           NO                                 BC10370 32300031
         BL    MLA#109       NO                                BC10918  32301031
         BCTR  R1,0   == YES-ADJUST POINTER TO VARIABLE ==      BC10370 32310027
MLA#109  DS    0H                                              BC10918  32311031
         LA    R14,1(R15,R2)     POINT TO BYTE TO BE VACATED    BC10370 32320027
         MVI   0(R14),C' '       CLEAR VACATED BYTE             BC10370 32330027
*     DONT CHG LINE PTR (R2), ONLY LEN (R15)                            32340027
         B     FNLSQZ2B                                         BC10370 32350027
MVFNLSQZ MVC   0(*-*,R2),1(R2)                                  BC10370 32360027
AFTSQZ   EQU   *                 AFTER FNLSQZ                 BC10370   32370027
AMPRSLP2 LH    R15,LINELEN                                       BC0283 32380027
         LA    R15,0(R15,R12)                                    BC0283 32390027
         SR    R15,R1                NUMBER OF CHARS AFTER &            32400027
         BCTR  R15,0                 SET FOR MVC                        32410027
         CLI   SHIFTEND,C'Y'         IS SHIFT AT END ONLY ?     BC10314 32420027
         JE    AMPRSLP6              YES - JUST DO THAT         BC10314 32430027
         CLC   =C'//',0(R12)                   JCL  LINE ?      BC10294 32440027
         JE    AMPRSLP6              YES- CONT WITH STD PROC    BC10294 32450027
         LA    R14,1(,R1)         NO-R14 -> VAR IN THE LINE     BC10294 32460027
AMPRSLP4 DS    0H                                               BC10294 32470027
         CLC   0(2,R14),=80C' '      DO WE HAVE 2 BLANKS ?      BC10294 32480027
         JE    AMPRSLP5              YES - COPY UP TO THEM      BC10294 32490027
         AHI   R14,1                 NEXT CHAR                  BC10294 32500027
         BCT   R15,AMPRSLP4                                     BC10294 32510027
AMPRSLP5 DS    0H                                               BC10294 32520027
         SR    R14,R1                R14 - LENGTH TILL 2 BLANKS BC10294 32530027
         LR    R15,R14               COPY FOR EX                BC10294 32540027
         AHI   R15,-1                FOR EX, ELIMINATE THE BLANKBC10294 32550027
AMPRSLP6 DS    0H                                               BC10294 32560027
*BC10450 LA    R14,2(R1,R15)  R1-> '&'; R15=LINELEN AFTR '&' -1BC10294  32570027
         LA    R14,1(R1,R15)  R1-> '&'; R15=LINELEN AFTR '&' -1BC10450  32580027
         CLI   0(R14),C' '        DO WE HAVE A BLANK FOR SHIFT? BC10294 32590027
         JE    AMPRSLP7           YES                           BC10294 32600027
         L     R2,SAVLENV    VAR LEN < 3?                    BC10450    32610027
         CHI   R2,3                                          BC10450    32620027
         BL    NOSQZ         CANT SQZ ANY FURTHER - DO ERRMSGBC10450    32630027
         ST    R9,SAVER9X     SAVE                           BC10450    32640027
         LARL  R9,INSERT   R15,R2 ARE PRESERVED              BC10450    32650027
         BALR  R9,R9                                         BC10450    32660027
         L     R9,SAVER9X     RESTORE                        BC10450    32660127
         MVC   80(80,R12),0(R12)                             BC10450    32660227
         MVC   0(80,R12),=80C' '                             BC10450    32660327
         MVC   0(12,R12),=C'%%SET %%X=%%'                    BC10450    32660427
         MVC   8(1,R12),VARNDX    REPLACE 'X' ABOVE W/ 0/1/2 BC10450    32660527
         AHI   R1,80          ADJUST R1 VARNM PTR AFTER INSRTBC10450    32660627
         LAY   R14,-1(,R2)    R14=VARNAME LEN-1 FOR 'EX'     BC10450    32660727
MLA#209  DS    0H                                              BC10918  32660846
         MVC   12(*-*,R12),1(R1)       VAR NAME              BC10450    32660927
*BC10918 EX    R14,*-6                                       BC10450    32661046
         EX    R14,MLA#209                                   BC10918    32661146
         AHI   R12,80                                        BC10450    32661246
         MVC   0(2,R1),=C'%%'    NOW UPDATE THE VAR IN JCL   BC10450    32661346
         MVC   2(1,R1),VARNDX        INDEX NUMB              BC10450    32661446
         IC    R0,VARNDX  INCREMENT FOR NXT VAR ON SAME LINE BC10450    32661546
         AHI   R0,1                                          BC10450    32661646
         STC   R0,VARNDX                                     BC10450    32661746
         SR    R15,R14 R14=VARNM LEN-1; R15=LINELEN AFTER &  BC10450    32661846
         LA    R14,1(R2,R1)              PNT PAST THE VARNM  BC10450    32661946
         EX    R15,TAILSHFT      R15=SHIFT LEN               BC10450    32662046
         LA    R14,1(R15,R1) POS OF TAIL TO CLEAR            BC10450    32662146
         AHI   R2,-3    ADJUST (2 FOR EXTRA %0, 1 FOR 'EX')  BC10450    32662246
         BM    SKPSHFT         NO TAIL TO CLEAR              BC10450    32662346
         EX    R2,TAILCLR                                    BC10450    32662446
         B     SKPSHFT                                       BC10450    32662546
TAILSHFT MVC   3(*-*,R1),0(R14)      MOVE TAIL OVER          BC10450    32662646
TAILCLR  MVC   3(*-*,R14),=80C' '  CLR VACATED TAIL CHARS    BC10450    32662746
NOSQZ    EQU   *                                             BC10450    32662846
         BAL   R2,WTOERMSG   NO-WRITE WTO ERR MSGS 1505E/6E   BC10370   32662946
AMPRSLP7 DS    0H                                               BC10294 32663046
         MVC   VARLINE,=80C' '                                          32663146
         EX    R15,MVCAMP1           MVC VARLINE(*-*),1(R1)             32663246
         EX    R15,MVCAMP2           MVC 2(*-*,R1),VARLINE              32664027
AMPRSLP3 EQU   *                                              BC10091   32665027
         MVC   0(2,R1),=C'%%'       REPLACE %/&/?                       32666027
SKPSHFT  EQU   *                                             BC10450X   32667027
         OI    FLAGS2,NOTEMP         NOT A &&-TEMP                      32668027
         CLC   =C'ODAY',2(R1)       IS THIS &ODAY                       32669027
         BNE   NOCONVRT             NO                                  32670027
         MVC   2(4,R1),=C'ZZZZ'     REPLACE ODAY WITH %%ZZZZ            32680027
*  WHICH IN TURN WILL BE REPLACED BY %%OWDAY                            32690027
NOCONVRT LA    R1,2(,R1)            POINT PAST && OR %%                 32700027
         LH    R15,LINELEN                                       BC0283 32710027
         LA    R15,0(R15,R12)                                    BC0283 32720027
         SR    R15,R1                NUMBER OF CHARS AFTER &            32730027
         BNP   AMPEND               END-OF-LINE                         32740027
         TM    FLAGS2,NOTEMP        IS IT &&-TEMP                       32750027
         BNO   AMPRSLP              YES                                 32760027
         NI    FLAGS2,X'FF'-NOTEMP                                      32770027
CHKDELIM L     R2,=A(DELIM)                                     WC0225  32780027
         EX    R15,TRTDELIM    TRT   0(*-*,R1),0(R2) FIND DELIM         32790027
         BZ    AMPEND               NONE- END                           32800027
         CLC   =C'..',0(R1)     CONCAT SOMETHING TO VAR W/ 2 DOTSBC0326 32810027
         BE    SQZPRD               CHK TO SQUEEZE OUT '.'       BC0326 32820027
         CLI   0(R1),C'.'       CONCAT SOMETHING TO VAR W/ 1 DOTBC10035 32830027
         BNE   SQZPRD2          NO                              BC10035 32840027
         CLI   1(R1),C'&&'      &A.&B OR &A.%B ?                BC10035 32850027
         BE    NOPERCNT         YES - CONTINUE                  BC10035 32860027
         CLI   1(R1),C'%'                                       BC10351 32870027
         BE    NOPERCNT                                         BC10351 32880027
* CHECK IF THERE IS A NON-% DELIM AFTER THE '.'; IF YES DELETE THE '.'  32890027
         L     R2,=A(DELIM)                                     BC10354 32900027
         TRT   1(1,R1),0(R2)  ANY OTHER DELIM BESIDES &, %      BC10354 32910027
         BNZ   SQZPRD0       YES - SQZ OUT PERIOD BEFORE IT     BC10354 32920027
         BCTR  R1,0             POINT BEFORE '.'                BC10035 32930027
         OI    FLAGS0,$CONCAT   INDIC FOR %%A%%.CONST           BC10035 32940027
         B     SQZPRD3                                          BC10035 32950027
SQZPRD2  EQU   *                                                 BC0326 32960027
         CLI   0(R1),C'&&'          &-VARIABLE NEXT?                    32970027
         BNE   CKPERCNT              NO                                 32980027
         CLI   1(R1),C'&&'          2 CONSECUTIVE &'S                   32990027
         BE    NOCONVRT         YES-TEMP FILE - DONT CONVERT            33000027
SQZPRD3  EQU   *                                                BC10035 33010027
         LH    R15,LINELEN                                       BC0283 33020027
         LA    R15,0(R15,R12)                                    BC0283 33030027
         SR    R15,R1                NUMBER OF CHARS AFTER &            33040027
         BCTR  R15,0                 SET FOR MVC                        33050027
         CLI   SHIFTEND,C'Y'         IS SHIFT AT END ONLY ?     BC10315 33060027
         JE    SQZPRDP6              YES - SQZ ONLY AT END      BC10315 33070027
         CLC   =C'//',0(R12)                   JCL  LINE ?      BC10294 33080027
         JE    SQZPRDP6              YES -CONT WITH STD SQZ PRC BC10294 33090027
         LA    R14,1(,R1)            R14 -> VAR IN THE LINE     BC10294 33100027
SQZPRDP4 DS    0H                                               BC10294 33110027
         CLC   0(3,R14),=80C' '      DO WE HAVE 3 BLANKS ?      BC10294 33120027
         JE    SQZPRDP5              YES - COPY UP TO THEM      BC10294 33130027
         AHI   R14,1                 NEXT CHAR                  BC10294 33140027
         BCT   R15,SQZPRDP4                                     BC10294 33150027
SQZPRDP5 DS    0H                                               BC10294 33160027
         SR    R14,R1                R14 - LENGTH TILL 3 BLANKS BC10294 33170027
         LR    R15,R14               COPY FOR EX                BC10294 33180027
         AHI   R15,-1                -1 FOR EX                  BC10294 33190027
SQZPRDP6 DS    0H                                               BC10294 33200027
         LA    R14,1(R1,R15)                                    BC10294 33210027
         CLC   0(2,R14),=80C' '  DO WE HAVE 2 BLANKS FOR SHIFT? BC10294 33220027
         JE    SQZPRDP7           YES                           BC10294 33230027
         BAL   R2,WTOERMSG   NO-WRITE WTO ERR MSGS 1505E/6E   BC10370   33240027
*BC10370 ST    R1,SAVER1                                        BC10294 33250027
*BC10370 ST    R15,SAVER15                                      BC10294 33260027
*BC10370 MVC   WTONS3+19(8),MEMBER                              BC10294 33270027
*WTONS3   WTO   'CTMOP1505E-XXXXXXXX OVERFLOW WHILE SHIFTING' BC10294   33280027
*BC10370 MVC   WTONS4+19(8),MEMBER                              BC10294 33290027
*BC10370 MVC   WTONS4+28(80),0(R12)                             BC10294 33300027
*TONS4   WTO   'CTMOP1506E-XXXXXXXX                                    X33310027
                                                                 '      33320027
*BC10370 L     R1,SAVER1                                        BC10294 33330027
*BC10370 L     R15,SAVER15                                      BC10294 33340027
SQZPRDP7 DS    0H                                               BC10294 33350027
         MVC   VARLINE,=80C' '                                          33360027
         EX    R15,MVCAMP1           MVC VARLINE(*-*),1(R1)             33370027
***?     CLC   =C'//',0(R12)      PROCESSING JCL LINE?         BC10370  33380027
***?     BE    *+6       YES - NO WORRY ABOUT OVFLW TO NXT LINEBC10370  33390027
         BCTR  R15,0            DONT KILL 1ST BYTE OF NEXT LINE  BC0358 33400027
         EX    R15,MVCAMP3           MVC 3(*-*,R1),VARLINE              33410027
         TM    FLAGS0,$CONCAT             %%A%%.CONST ?         BC10035 33420027
         BO    SQZPRD4                    YES                   BC10035 33430027
         MVC   0(3,R1),=C'.%%'                                          33440027
         CLC   =C'ODAY',3(R1)       IS THIS &ODAY                       33450027
         BNE   NOCONVR2             NO                                  33460027
         MVC   3(4,R1),=C'ZZZZ'     REPLACE ODAY WITH %%ZZZZ            33470027
*NOCONVR2 LA    R1,3(,R1)            POINT PAST .%%            BC10370  33480027
NOCONVR2 LA    R1,1(,R1)   POINT PAST '.' @NOCONVRT PT PAST %% BC10370  33490027
*BC0358  SH    R15,=H'3'            BYTES REMAINING                     33500027
*BC10370 SH    R15,=H'2'            BYTES REMAINING              BC0358 33510027
*BC10370 BNP   AMPEND               NONE - END                          33520027
*BC10370 B     CHKDELIM                                                 33530027
         B     NOCONVRT             POINT PAST %% & CONTINU    BC10370  33540027
SQZPRD4  EQU   *                                                BC10035 33550027
         MVC   1(2,R1),=C'%%'   &A.CONST --> %%A%%.CONST        BC10035 33560027
         NI    FLAGS0,X'FF'-$CONCAT       RESET                 BC10035 33570027
         LA    R1,1(,R1)                                        BC10035 33580027
         B     NOCONVRT                                         BC10035 33590027
CKPERCNT CLI   0(R1),C'%'           DELIM IS A %-VARIABLE?              33600027
         BNE   NOPERCNT             NO                                  33610027
         CLI   1(R1),C'%'           ALREADY TRANSLATED?                 33620027
         BNE   AMPRSLP2                       NO                        33630027
         LA    R1,2(,R1)                      YES                       33640027
NOPERCNT LH    R15,LINELEN                                       BC0283 33650027
         LA    R15,0(R15,R12)                                    BC0283 33660027
         SR    R15,R1                NUMBER OF CHARS AFTER DELIM        33670027
         B     AMPRSLP                                                  33680027
SQZPRD0  AHI   R1,-2            POINT BACK BEFORE THE PERIOD   BC10354  33690027
SQZPRD   L     R15,=A(AMPERSND)    CONSTANT AFTER ..? BC0326 BC10091    33700027
         TRT   2(1,R1),0(R15)      CONSTANT AFTER ..? BC0326 BC10091    33710027
         BNZ   NOPERCNT              NO - ANOTHER VARIABLE      BC0326  33720027
         LH    R15,LINELEN           YES                        BC0326  33730027
         LA    R15,0(R15,R12)                                   BC0326  33740027
         SR    R15,R1                NUMBER OF CHARS AFTER ..   BC0326  33750027
*BC10370 AHI   R15,-2                SET FOR MVC                BC10354 33760027
*  THE PRIOR EXPANSION OF THE LINE DUE TO & --> %% MAY HAVE OVFLWED     33770027
         BCTR  R15,0       HENCE THE LEN INCLUDES COL72/80     BC10370  33780027
MLA#210  DS    0H                                              BC10918  33781046
         MVC   1(*-*,R1),2(R1)       SQUEEZE OUT (2ND) '.'      BC0326  33790027
*BC10918 EX    R15,*-6                                          BC0326  33800046
         EX    R15,MLA#210                                     BC10918  33801046
         LA    R15,2(R15,R1)      AFTR SQZ, BLNK TRAILING BYTE BC10354  33810027
         MVI   0(R15),C' '                                     BC10354  33820027
         B     SQZPRD2                                          BC0326  33830027
*BC10273 AMPEND   L     R15,SAVER15                                     33840027
AMPEND   DS    0H                                               BC10273 33850027
         LHI   R15,0                                            BC10273 33860027
         J     AMPRTR                                           BC10273 33870027
*                                                                       33880027
WTOERMSG ST    R1,SAVER1           WTO OVERFLOW RTN    BC10294 BC10370  33890027
         ST    R15,SAVER15                                      BC10294 33900027
*BC10370 MVC   WTONS1+19(8),MEMBER                              BC10294 33910027
*TONS1 WTO 'CTMOP1505E-XXXXXXXX OVERFLOW WHILE SHIFTING' BC10294BC10370 33920027
*BC10893 MVC   WTONS2+19(8),MEMBER                              BC10294 33930028
         MVC   ERR03MEM(8),MEMBER    MOVE THE MEMBER NAME       BC10893 33931029
*BC10893 MVC   WTONS2+28(80),0(R12)                             BC10294 33940028
         MVC   ERR03DES(80),0(R12)   MOVE THE DES OF ERROR      BC10893 33941029
*BC10893 WTO   'CTMOP1506E-XXXXXXXX                                    X33950028
                                                                 '      33960027
         L     R1,ERROR         LOAD THE DCB'S ADDRES OF MSG    BC10893 33961029
         PUT   0(R1),ERROR003        WRITE THE MESSAGE          BC10893 33962029
         L     R1,SAVER1                                        BC10294 33970027
         L     R15,SAVER15                                      BC10294 33980027
         BR    R2                                            BC10370    33990027
CHKQMARK EQU   *                                                BC10351 34000027
         TM    FLAGS1,$VARXST   WAS THERE A PREVIOUS VAR ON LINEBC10351 34010027
         BNO   QMARKOK     NO- CONTINU PROCESSING THE VAR       BC10351 34020027
AMPERR   DS    0H                                               BC10273 34030027
         LHI   R15,8                 SIGN ERROR IN CARD         BC10273 34040027
AMPRTR   DS    0H                                                       34050027
         L     R1,CHKAMPPA                                      BC10273 34060027
         ST    R12,0(,R1)  UPDATE PARAMETER TO BE USED BY CALLERBC10273 34070027
         ST    R11,4(,R1)  UPDATE PARAMETER TO BE USED BY CALLERBC10273 34080027
         BRTRN (15)                                             BC10273 34090099
**       SUBXRET                                                BC10918 34090299
*-------------------------------------------------------------  BC10273 34091035
*WC10076 .NOTESA7 ANOP                                           WC0001 34100027
*BC10273 NOTESA7  DS    0H                                     WC10076  34110027
*BC10450 BR    R9                                                       34120027
*BC10273 QVAR     EQU   *   ?-VARIABLE PROCESSING              WC10049  34130027
*BC10273 ST    R9,SAVER9    SET FOR PROPER RETURN AFTER ERR    WC10049  34140027
*BC10273 B     OPCERR                                          WC10049  34150027
*-------------------------------------------------------------  BC10273 34151035
IOAMEERA NI    FLAGS0,X'FF'-MULTSYSN      RESET FLAG             WC0467 34160027
         L     R1,ERROR               DCB ADDR FOR MSGS          WC0467 34170027
         ST    R1,IMOUTDCB                                       WC0467 34180027
         CALL  IOAGBE,(IMSTART)       IOAMEM ERROR MSG           WC0467 34190027
         BR    R10                                               WC0467 34200027
*-------------------------------------------------------------  BC10273 34201035
*==REQUIRES %%RANGE STMT TO PREVENT LINE FROM SHIFTING                  34210027
*==SPECIFY %%RANGE 01 NN+LEN+1 WHERE NN IS FROM ?NNVAR AND LEN IS THE   34220027
*==THE LENGTH OF THE VARIABLE NAME                                      34230027
*==AFTER THE JCL LINE THE RANGE MUST BE RESTORED TO '1 80'              34240027
**       LA    R15,AMPEND       IN CASE OF ERROR - RETURN ADDR WC10049  34250027
**       ST    R15,SAVER9                                      WC10049  34260027
**       L     R15,=A(NUMTAB)                                  WC10049  34270027
**       TRT   1(2,R1),0(R15) 2-DIGITS MUST FOLLOW THE '?'     WC10049  34280027
**       BNZ   OPCERR           NOT NUMERIC - NOT SUPPORTED    WC10049  34290027
**       PACK  WORK,1(2,R1)     PACK THE NUMERIC COL #         WC10049  34300027
**       CVB   R15,WORK                                        WC10049  34310027
**       STH   R15,SAVCOL       AND SAVE COL#                  WC10049  34320027
**       LAY   R15,-1(R15,R12)  POINT TO COL OFFSET IN LINE    WC10049  34330027
**       CLI   0(R15),C' '      IS IT BLANK                    WC10049  34340027
**       BNE   OPCERR           NOT SUPPORTED                  WC10049  34350027
**       ST    R1,SAVPOS        SAVE ADDR OF '?'               WC10049  34360027
**       LA    R15,3(,R1)       POINT PAST '?NN' TO VAR-NAME   WC10049  34370027
**       L     R2,=A(DELIM)     CALC LENG OF ?-VAR             WC10049  34380027
**       TRT   0(9,R15),0(R2)   BY FINDING DELIM (ADDR IN R1)  WC10049  34390027
**       STC   R2,SAVDELIM      SAVE DELIM:'.' MUST BE CARRIED WC10049  34400027
**       SR    R1,R15           R1=ACTUAL LENG OF VAR-NAME     WC10049  34410027
**       L     R2,=A(VARTBL)   VERIFY ?-VAR IS A SYSTEM VAR    WC10049  34420027
**VARTBLP  EQU   *    VAR-NAME-LENG IS 1-BYTE IN VARTBL+8      WC10049  34430027
**       CLI   0(R2),X'FF'     LAST ELEMENT IN TBL?            WC10049  34440027
**       BE    ...              NOT A SUPPORTED SYSTEM VAR     WC10049  34450027
** MARK MEMBR AS CHANGED                                                34460027
**       CLM   R1,1,8(R2)      SAME LENG AS VAR IN TBL?        WC10049  34470027
**       BNE   VARTBLP2         KEEP LOOPING                   WC10049  34480027
**       LAY   R14,-1(,R1)      ADJUST LEN FOR CLC             WC10049  34490027
**       EX    R14,CLCQVAR      MATCH VAR IN TBL               WC10049  34500027
**       BNE   VARTBLP2     NO- KEEP LOOPING                   WC10049  34510027
* CHECK IF THERES ENOUGH BLANKS JUST TO MOVE THE VAR IN                 34520027
**       MVC   SAVVALLN,8+1(R2) SAVE LENG OF VALUE             WC10049  34530027
**       LA    R2,1(,R1)        R2=ACTUAL-LEN+1 (FOR '%%')     WC10049  34540027
**       CLI   SAVDELIM,C'.'   IS THERE A VAR-DELIM OF '.'     WC10049  34550027
**       BNE   *+8             NO                              WC10049  34560027
**       LA    R2,1(,R2)       CARRY IT ALONG WITH VARNAME     WC10049  34570027
**       LH    R1,SAVCOL       GET TARGET COL                  WC10049  34580027
**       LAY   R1,-1(R1,R12)     POS ON LINE                   WC10049  34590027
**       EX    R2,CLCBLNK      ENOUGH ROOM FOR %%VAR-NAME.     WC10049  34600027
**       BNE   .....       NO- SQEEZE IN VARNM BY EXPANDNG LINEWC10049  34610027
**       MVC   0(2,R1),=C'%%'  A-E VAR                         WC10049  34620027
**       LAY   R2,-2(,R2)      ADJUST LENG (NOT MOVING THE %%) WC10049  34630027
**       EX    R2,MVCQVAR      MOVE THE VAR TO TARGET COL      WC10049  34640027
**       LA    R2,3(,R2)       ADJ LENG TO CLR ?NNVARNM.       WC10049  34650027
**       L     R1,SAVPOS       RESTORE POS OF ?NNVAR           WC10049  34660027
**       EX    R2,CLRQVAR      BLANK OUT THE CURR POS OF ?NNVARWC10049  34670027
**       B     NOPERCNT        R1 POINTS TO CLEARED ?-VAR      WC10049  34680027
*VARTBLP2 EQU   *                                               WC10049 34690027
**       LA    R2,L'VARTBL(,R2)   NEXT ENTRY IN VAR TBL        WC10049  34700027
**       B     VARTBLP            KEEP TYING                   WC10049  34710027
*                                                                       34720027
**CLCBLNK  CLC  0(*-*,R1),=80C' '  ENOUGH BLANK SPACE IN TARGET?WC10049 34730027
**CLCQVAR  CLC  0(*-*,R15),0(R2) COMP  VAR IN TBL, R15=A(?NNVAR)WC10049 34740027
**MVCQVAR  MVC  2(*-*,R1),0(R15)   MOVE VAR-NAME (+DELIM)       WC10049 34750027
**CLRQVAR  MVC  0(*-*,R1),=80C' '  CLR ?NNVAR-NAME (+DELIM)     WC10049 34760027
*TRTAMPRS TRT   0(*-*,R1),AMPERSND   ANY &'S, %'S OR ?'S       BC10091  34770027
TRTAMPRS TRT   0(*-*,R1),0(R2) ANY &'S, %'S OR ?'S    BC10091           34780027
TRTDELIM TRT   0(*-*,R1),0(R2)  FIND VARIABLE DELIMITER WC0225          34790027
MVCAMP1  MVC   VARLINE(*-*),1(R1)                                       34800027
MVCAMP2  MVC   2(*-*,R1),VARLINE                                        34810027
MVCAMP3  MVC   3(*-*,R1),VARLINE                                        34820027
*                                                                       34830027
ADDINCLB ST    R9,SAVER9X        SAVE                                   34840027
         ST    R14,SAVER14       SAVE                                   34850027
         TM    FLAGS2,FIRSTINC   ALREADY INSERTED INCLIB 'SYSTEM'?      34860027
         BO    ADDEND                  YES                              34870027
*BC10091 ST    R1,SAVER1               NO                               34880027
*BC10093 ST    R1,SAVER1_2             NO                    BC10091    34890027
         ST    R1,SAVER1               NO                    BC10093    34900027
         OI    FLAGS2,FIRSTINC                                          34910027
*WC10076 AIF   ('&GTABLE' EQ ' ').NGTABLE  SKIP WHEN BLNK    BC10024    34920027
         CLI   GTABLE,C' '                                      WC10076 34930027
         BE    NGTABLE                                          WC10076 34940027
*BC10273 BAL   R9,INSERT                   ADD GLOBL          BC0102    34950027
         LARL  R9,INSERT                                        BC10273 34960027
         BALR  R9,R9                       ADD GLOBL            BC10273 34970027
         MVC   80(80,R12),0(R12)                              BC0102    34980027
         MVC   0(80,R12),=80C' '                              BC0102    34990027
*WC10076 MVC   0(L'GTABLE,R12),GTABLE                         BC0102    35000027
         MVC   0(L'GTABLE@,R12),GTABLE@                         WC10076 35010027
*WC10076 MVC   L'GTABLE(8,R12),=CL8'&GTABLE'                  BC0102    35020027
         MVC   L'GTABLE@(8,R12),GTABLE                          WC10076 35030027
         LA    R12,80(,R12)            POINT PAST THE GLOBL   BC0102    35040027
NGTABLE  DS    0H                                               WC10076 35050027
*BC10273 BAL   R9,INSERT                   DO IT NOW                    35060027
         LARL  R9,INSERT                                        BC10273 35070027
         BALR  R9,R9                       DO IT NOW            BC10273 35080027
         MVC   80(80,R12),0(R12)                                        35090027
         MVC   0(80,R12),=80C' '                                        35100027
         L     R1,=A(INCLIB)                                 BC10370    35110027
         MVC   0(L'INCLIB,R12),0(R1)                         BC10370    35120027
*BC10217 MVC   L'INCLIB(6,R12),=C'SYSTEM'                               35130027
         MVC   L'INCLIB(8,R12),=C'CNVOPCIN' COPY SUPPLIED NAME  BC10217 35140027
         LA    R12,80(,R12)            POINT PAST THE INCLIB            35150027
*BC10093 L     R1,SAVER1_2                                   BC10091    35160027
         L     R1,SAVER1                                     BC10093    35170027
*BC10025 LA    R1,160(,R1)       SET R1 TO POINT CORRECTLY    BC0282    35180027
*WC10076 AIF   ('&GTABLE' EQ ' ').NGTABL2                    BC10025    35190027
         CLI   GTABLE,C' '                                      WC10076 35200027
         BE    NGTABL2                                          WC10076 35210027
         LA    R1,80(,R1)       SET R1 TO POINT CORRECTLY    BC10025    35220027
NGTABL2  DS    0H                                               WC10076 35230027
         LA    R1,80(,R1)       SET R1 TO POINT CORRECTLY    BC10025    35240027
         ST    R1,SAVER1  IN PREPARATN OF RESTORING R1 LATER BC10093    35250027
ADDEND   L     R9,SAVER9X                                               35260027
         L     R14,SAVER14                                              35270027
         BR    R14                                                      35280027
*BC10918 DROP  R8                                              BC10273  35300063
         AGO   .ENDCODE                                        BC10273  35310027
*-------------------------------------------------------------  BC10273 35311050
.AFCHKAMP ANOP                                                 BC10273  35320027
QVAR     EQU   *            ?-VARIABLE PROCESSING              BC10273  35330027
         ST    R9,SAVER9    SET FOR PROPER RETURN AFTER ERR    BC10273  35340027
         B     OPCERR                                          BC10273  35350027
OPCERR   EQU   *                                                        35360027
         MVI   FLAGR,0     RESET ALL CONTINUATION FLAGS!     BC10758    35370027
*BC10893 MVC   WTO+19(8),MEMBER                                         35380028
         MVC   ERR04MEM(8),MEMBER   MOVE THE MEMBER NAME       BC10893  35381029
         TM    FLAGS0,SYSINPDS      PROCESSING A SYSIN PDS MEM?BC10433  35390027
*BC10918 BNO   *+10                 NO                         BC10433  35400031
         BNO   MLA#110              NO                         BC10918  35401031
*BC10893 MVC   WTO+19(8),SYSINMEM   YES                        BC10433  35410028
         MVC   ERR04MEM(8),SYSINMEM YES                        BC10893  35411028
MLA#110  DS    0H                                              BC10918  35412031
*BC10893 MVC   WTO+28(80),0(R12)                                        35420028
         MVC   ERR04DES(80),0(R12)  MOVE THE DESC OF ERROR     BC10893  35421029
*BC10893 WTO   'CTMOP1501E-XXXXXXXX                                    X35430028
                                                                 ',    X35440027
               ROUTCDE=11                                               35450027
         L     R1,ERROR          LOAD THE DCB'S ADDRESS OF MSG BC10893  35460029
         PUT   0(R1),ERROR004        WRITE THE MSG             BC10893  35470029
         CLM   R9,7,=AL3(BALRRET)     COMING FROM RECOV SUBPARM WC0244  35487027
         BER   R9          YES - DONT RETURN TO MAIN RTN WC0244         35488027
         L     R9,SAVER9                                                35489027
         BR    R9                                                       35490027
*-------------------------------------------------------------  BC10273 35500050
*                                                                       35522027
ERRMSG   EQU   *                                             WC0225     35523027
*BC10893 MVC   WTO2+27(8),MEMBER     SET JOBNAME IN MSG      WC0225     35524028
         MVC   ERR05MEM(8),MEMBER   MOVE THE MEMBER NAME     BC10893    35524129
*BC10893 WTO   'CTMOP015-00E - JOB=XXXXXXXX, OPC BATCH      COMMAND XXX*35525028
               XXXX COULD NOT BE CONVERTED, RC=XX'           WC0225     35526027
         L     R1,ERROR     LOAD THE DCB'S ADDRESS OF MSG    BC10893    35526129
         PUT   0(R1),ERROR005    WRITE THE MSG               BC10893    35526229
         BR    R9                                            WC0225     35527027
EXECADDR DS    F                                                BMBMBM  35529027
                                                                        35529129
         DROP  ,                                                        41840099
*-------------------------------------------------------------- BC10918 41850034
**TVARS  SUBXSET                                               BC10918  41860099
GETVARS  DS    0F                                               BC10918 41861099
         BEGIN GETVARS                                                  41870099
         L     R8,=A(CTMO15WS)                                  BC10918 41871099
         LAY   R5,4096(,R8)                                     BC10918 41871199
         USING CTMO15WS,R8,R5                                   BC10918 41871299
*        RETRIEVE DEFAULT VARIABLES                                     41880027
         CTMCDFVL REQUEST=CREATE,                               WC10076X41890027
               ADDRESS=DEFBLOCK                                 WC10076 41900027
         L     R7,DEFBLOCK                                      WC10076 41910027
*BC10918 L     R8,=A(VARTAB)                                            41920063
         L     R9,=A(VARVALS)                                           41930027
         CTMCDFVL REQUEST=RETRIEVE,                             WC10076X41940027
               ADDRESS=(R7),                                    WC10076X41950027
               VARTAB=VARTAB,                                          X41960063
               VARCNT=NUMVAR,                                          X41970027
               VALUE=(R9),                                             X41980027
               MF=(E,MFCALL)                                            41990027
         BXH   R15,R15,VARABND                                          42000027
*        READ DSN TRANSLATION TABL: OLD DSN VS. NEW DSN                 42010027
         OPEN  (DSNTRAN,INPUT)                                          42020027
         LTR   R15,R15                                                  42030027
         BNZ   DSNTERR                                                  42040027
         L     R0,=A(DSNMAX*88)                                         42050027
         GETMAIN RU,LV=(0),LOC=ANY                                      42060027
*BC10918 USING VARTAB,R8                                                42070063
         ST    R1,DSNTRA                                                42080027
         LR    R4,R1                                                    42090027
         AR    R1,R0                                                    42100027
         LR    R6,R1                                                    42110099
DSNTLOOP DS    0H                                                       42120027
         CR    R4,R6                                            WC10076 42130099
         BNL   DSNSPERR                                         WC10076 42140027
         NI    FLAGDSN,255-$NEW_NAME_EXPECTED                   WC10076 42150027
         GET   DSNTRAN                                                  42160027
         MVC   0(44,R4),0(R1)                                           42170027
         OI    FLAGDSN,$NEW_NAME_EXPECTED                       WC10076 42180027
         GET   DSNTRAN                                                  42190027
         MVC   44(44,R4),0(R1)                                          42200027
         LA    R4,88(0,R4)                                              42210027
         B     DSNTLOOP                                                 42220027
DSNTEOF  DS    0H                                                       42230027
         TM    FLAGDSN,$NEW_NAME_EXPECTED                       WC10076 42240027
         BZ    PAIROK                                                   42250027
         WTO   'CTMOP015: DSN PAIR (NEW) EXPECTED'                      42260027
         ABEND 191                                                      42270027
PAIROK   DS    0H                                                       42280027
         ST    R4,DSNTRE                                                42290027
         SR    R6,R4                                                    42300099
         BNP   DSNOVFR                                                  42310027
         FREEMAIN RU,LV=(R6),A=(R4)                                     42320099
DSNOVFR  DS    0H                                                       42330027
         CLOSE DSNTRAN                                                  42340027
         BRTRN 0                                                        42350099
**       SUBRRET 0                     |exit Subroutine         BC10918 42351099
*BC10918 DROP  R8                                                       42360063
VARABND  DS    0H                                                       42370027
         WTO   'CTMOP015-DEFAULT: VARIABLE NOT FOUND'                   42380027
         ABEND 189                                                      42390027
DSNTERR  WTO   'CTMOP015-DSN TRANSLATION TABLE NOT PROVIDED'            42400027
         ABEND 190                                                      42410027
DSNSPERR WTO   'CTMOP015-INSUFFICIENT STORAGE FOR DSN TABLE'            42420027
         ABEND 191                                                      42430027
         DROP ,                                                 BC10273 42440099
*----                                                                   42500027
*-------------------------------------------------------------- BC10918 42501034
* CHKJSET -                                                             42610027
*   IF R1=0                                                             42620027
*     THEN                                                              42630027
*       CHECK THE CARD POINTED BY R12.                                  42640027
*       IF "//  SET"                                                    42650027
*         THEN                                                          42660027
*           EXTRACT VARIABLE NAME                                       42670027
*           ADD NAME TO TABL                                            42680027
*           RETURN R15=0                                                42690027
*         ELSE                                                          42700027
*           RETURN R15=8                                                42710027
*     ELSE (R1 -> & OF A VAR NAME)                                      42720027
*       IF VAR IN TABL                                                  42730027
*         THEN                                                          42740027
*           RETURN R15=0                                                42750027
*         ELSE                                                          42760027
*           RETURN R15=8                                                42770027
* R11 AND R12 MUST BE RESET IN CASE OF CONTINUED 'SET' STMT  BC10758    42780027
*                    IF JCL SET CARD, EXTRACT THE VAR NAME      BC10268 42790099
*BC10918 SUBXSET                                                BC10918 42791099
CHKJSET  DS    0F                                               BC10918 42792099
         BEGIN CHKJSET                AND SEARCH LIN VAR LIST   BC10268 42800099
         L     R8,=A(CTMO15WS)                                  BC10918 42801099
         LAY   R5,4096(,R8)                                     BC10918 42801199
         USING CTMO15WS,R8,R5                                   BC10918 42802099
         ST    R12,JSLINPTR  CURR LINE PTR FOR MULTI-LINE 'SET' BC10758 42810027
         ST    R11,JSLINCTR  CURR LINE CTR FOR MULTI-LINE 'SET' BC10758 42820027
         ST    R2,ERROR1   STORE THE ADDRES OF DCB'S ERROR MSG  BC10893 42821029
         LTR   R4,R1               R4 -> VAR OR 0               BC10268 42830027
         JNZ   JSLOOKIT            VAR - LOOK IN TABL           BC10268 42840027
         L     R14,=A(BLANK)                                    BC10268 42850027
         TRT   2(9,R12),0(R14)                                  BC10268 42860027
         JZ    JSNOJSET            NAME TOO LONG - BACK WITH 8  BC10268 42870027
*        ST    R1,ENDSTEPA         SAVE ADDR OF END OF STEPNAME BC10268 42880027
         L     R14,=A(NONBLANK)                                 BC10268 42890027
         TRT   0(14,R1),0(R14)     LOOK FOR VERB                BC10268 42900027
         JZ    JSNOJSET                                         BC10268 42910027
         CLC   =C'SET ',0(R1)      Q. IS IT SET CARD?           BC10268 42920027
         JNE   JSNOJSET            A. NO - BACK WITH 8          BC10268 42930027
*BC10758 ST    R12,JSLINPTR  CURR LINE PTR FOR MULTI-LINE 'SET'BC10450  42940027
*  LOOK FOR NAME AND EXTRACT                                    BC10268 42950027
CHKJS1   EQU   *        ON CONTINU LINE SEARCH AFTR '// '      BC10450  42960027
*BC10450 TRT   4(60,R1),0(R14)   LOOK FOR START OF VAR AFTR SET BC10268 42970027
         TRT   3(60,R1),0(R14)   LOOK FOR START OF VAR AFTR SET BC10268 42980027
         JZ    JSNOJSET                                         BC10268 42990027
CHKJS2   EQU   *                                               BC10450  42991027
         LR    R4,R1               R4 -> VAR NAME IN SET CARD   BC10268 42992027
         L     R14,=A(DELIM)       LOOK FOR END OF VAR          BC10268 42993027
*BC10469 TRT   0(L'JSTVAR+1,R4),0(R14) ANY DELIMITER (=,' ')    BC10268 42994027
         TRT   1(L'JSTVAR+1,R4),0(R14) ANY DELIMITER (=,' ')    BC10469 42995027
*      START THE TRT AT OFFSET 1 TO SKIP OVER POSSIBLE '&' PFX          42996027
         JZ    JSNOJSET                                         BC10268 42997027
         CLI   0(R1),C'='          FOUND '=' DELIMETER ?        BC10469 42998027
         JZ    EQLDELIM            YES                          BC10469 42999027
         MVI   LONGSET,C'Y'    INDICATE EMBEDDED DLM IN VARNAME BC10469 43000027
*  SAV POS OF CHAR AFTER '=' DELIM; WE MAY HAVE QUOTED VAL W/ EMBEDDED  43010027
*  BLNKS/COMMAS.                                                        43020027
EQLDELIM DS    0H                                               BC10469 43030027
         LA    R2,1(,R1)      SAV POS OF VALU DELIM (IF ANY)   BC10456  43031027
         ST    R2,VALDELIM                                     BC10456  43032027
         MVC   JSTVAR,JSTEMPTY     INIT TO BLANKS (EMPTY)       BC10268 43033027
         SR    R1,R4               R1 - LEN                     BC10268 43034027
         CHI   R1,8        VAR LEN > 8?                        BC10758  43035027
         BH    JSERR       YES - INVALID                       BC10758  43036027
*BC10433 AHI   R1,-1               FOR EX                       BC10268 43037027
         BCTR  R1,0                FOR EX                       BC10433 43038027
         EX    R1,JSTAKEVR        MVC   JSTVAR(*-*),0(R4)       BC10268 43039027
         CLI   LONGSET,C'Y'   IS VAR NAME W/EMBED DELIM ?       BC10469 43040027
         JNZ   ADDTOTBL            NO                           BC10469 43050027
         L     R1,=A(MEMBER)  R1 <- ADDR CURR MEMBER NAME       BC10469 43060027
*BC10893 MVC   SETVRMSG+13(8),0(R1)         COPY MEMBER NAME    BC10469 43070028
         MVC   ERR06MEM(8),0(R1)         COPY MEMBER NAME       BC10893 43071028
*BC10893 MVC   SETVRMSG+56(30),0(R4)   COPY UNRESOLVED VAR NAME BC10469 43080028
         MVC   ERR06VAR(30),0(R4)   COPY UNRESOLVED VAR NAME    BC10893 43080128
*BC10893 WTO   TEXT=SETVRMSG  PRINT SET VAR NAME UNRESOLVED MSG BC10469 43081028
         L     R2,ERROR1      LOAD THE DCB'S ADDRESS MSG ERROR  BC10893 43081129
         PUT   0(R2),ERROR006   WRITE THE MSG                   BC10893 43081229
         MVI   LONGSET,C'N'       CLEAR VAR NAME FLAG           BC10469 43082027
         J     JSADD2                                           BC10469 43083027
*  ADD TO TABL                                                  BC10268 43084027
ADDTOTBL DS    0H                                               BC10469 43085027
         ST    R4,JSVARPOS    SAVE VARIABLE POS ON SET STMT    BC10450  43086027
         LA    R4,JSTABLE          R4 -> TABL OF FOUND VARS     BC10268 43087027
         LHI   R6,JSTABLE#         500                          BC10268 43088099
JSADDLP  DS    0H                                               BC10268 43089027
         CLC   JSTVAR,0(R4)        ALREADY IN TABL ?            BC10268 43090027
         JE    JSADDED             YES- EXIT WITH RC=0          BC10268 43100027
         CLC   JSTEMPTY,0(R4)      EMPTY ENTRY FOUND ?          BC10268 43110027
         JE    JSADDTOT            ADD TO TABL                  BC10268 43120027
         AHI   R4,L'JSTVAR         NEXT NETRY                   BC10268 43130027
         BCT   R6,JSADDLP          CHECK NEXT                   BC10268 43140099
*BC10758 WTO   'TOO MANY SET VARIABLES IN A SINGLE JCL MEMBER'  BC10268 43150027
JSERR    WTO   'TOO MANY SET VARIABLES IN MEMBER OR VAR TOO LONG' 10758 43160027
         LHI   R15,16              RC=16 - NO SPACE FOR VAR     BC10268 43170027
         J     JSEXIT              EXIT                         BC10268 43180027
JSADDTOT DS    0H                                               BC10268 43190027
         MVC   0(L'JSTVAR,R4),JSTVAR  COPY TO TABL              BC10268 43200027
JSADDED  DS    0H                                               BC10268 43210027
         L     R4,JSVARPOS   VAR POS ON LINE                   BC10450  43220027
*  IF THE VAR VALUE IS ENCLOSED IN QUOTES, FIRST FIND END-QUOT          43230027
         XR    R0,R0             QUOTES COUNT                   BC10758 43240027
         L     R1,VALDELIM       VAL DELIM IS A QUOT ?        BC10456   43241027
         CLI   0(R1),C''''                                    BC10456   43241127
         BNE   JSADD2               NO                        BC10456   43241227
REPQUOT1 EQU   *                                                BC10758 43241427
         AHI   R0,1              +1 TOS COUNT                   BC10758 43241527
         LA    R1,1(,R1)         POINT TO THE NEXT POS          BC10758 43241627
         CLI   0(R1),C''''       IS IT A QUOT AS WELL?          BC10758 43241727
         BE    REPQUOT1          YES - CHECK NEXT SYMBOL        BC10758 43241827
*        NIHL  R0,1              EVEN NUMBER OF QUOTES?         BC10758 43242027
         N     R0,=F'1'          EVEN NUMBER OF QUOTES?         BC10758 43242127
         BZ    JSADD3           YES - EMPTY vALUE               BC10758 43242227
FNDQUOT2 EQU   *                 FIND CLOSING QUOT              BC10758 43242427
         L     R14,=A(QUOTAB)       YES                       BC10456   43242527
*BC10758 TRT   1(60,R1),0(R14)        FIND END-QUOT           BC10456   43242627
         TRT   0(60,R1),0(R14)        FIND END-QUOT             BC10758 43242727
         BNZ   EQUOTFND                                         BC10758 43242827
*     END-QUOT PROBABLY LOCATED ON THE NEXT LINE                BC10758 43242927
         L     R1,JSLINCTR    ADJ LIN COUNTER                  BC10758  43243027
         BCTR  R1,0           TO RESTORE R11                   BC10758  43243127
         ST    R1,JSLINCTR                                     BC10758  43243227
         L     R1,JSLINPTR    CURRENT LINE POINTR              BC10758  43243327
         AHI   R1,80          SET R1 TO PROCESS VARS ON NXT LINBC10758  43243427
         ST    R1,JSLINPTR    TO RESTORE R12                   BC10758  43243527
         B     FNDQUOT2                                         BC10758 43243727
EQUOTFND EQU   *          END-QUOT FOUND                        BC10758 43243827
         AHI   R1,1                POINT TO CHAR AFTER QUOT   BC10456   43243927
         CLI   0(R1),C''''       IS IT A REPEATED QUOT?         BC10758 43244027
         BE    EQUOTFND          CHECK NEXT POSITION            BC10758 43244127
*                                                               BC10758 43244227
         B     JSADD3                                         BC10456   43244327
JSADD2   EQU   *                                              BC10456   43244427
         L     R14,=A(COMMABLK)  SEARCH FOR BLNK OR COMA       BC10450  43244527
         TRT   0(65,R4),0(R14)                                 BC10450  43244627
JSADD3   EQU   *                                              BC10456   43244727
         CLI   0(R1),C' '        BLNK MEANS NO MORE PARAMS     BC10450  43244827
         BNE   JSCONT            FOUND A COMMA                 BC10450  43244927
         LHI   R15,0    0=ADDED TO TBL; NO MORE VARS ON SET     BC10268 43245027
         J     JSEXIT              EXIT WITH RC=0               BC10268 43246027
JSCONT   EQU   *                                               BC10450  43247027
         AHI   R1,1           SKP THE COMA                     BC10450  43248027
         CLI   0(R1),C' '     MORE VARS ON SAME LINE ?         BC10450  43249027
         BNE   CHKJS2         YES                              BC10450  43250027
         L     R1,JSLINCTR    ADJ LIN COUNTER                  BC10758  43260027
         BCTR  R1,0           TO RESTORE R11                   BC10758  43261027
         ST    R1,JSLINCTR                                     BC10758  43261127
         L     R1,JSLINPTR    CURRENT LINE POINTR              BC10450  43261227
         AHI   R1,80          SET R1 TO PROCESS VARS ON NXT LINBC10450  43261327
         ST    R1,JSLINPTR    SAV FOR FOLLOWING LINES          BC10450  43261427
         L     R14,=A(NONBLANK)   PREPARE FOR TRT AFTR BRANCH  BC10450  43261527
         B     CHKJS1         PROCESS VARS ON CONTINUED SET LINBC10450  43261627
JSLOOKIT DS    0H                                               BC10268 43261727
*  LOOK FOR NAME IN TABL                                        BC10268 43261827
         AHI   R4,1                R4 - OVER THE &              BC10268 43261927
         L     R14,=A(DELIM)       LOOK FOR END OF VAR          BC10268 43262027
         TRT   0(L'JSTVAR+1,R4),0(R14) ANY DELIMITER (=,' ')    BC10268 43263027
         JZ    JSNOCONV                                         BC10268 43264027
         MVC   JSTVAR,JSTEMPTY     INIT TO BLANKS (EMPTY)       BC10268 43265027
         SR    R1,R4               R1 - LEN                     BC10268 43266027
         AHI   R1,-1               FOR EX                       BC10268 43267027
         EX    R1,JSTAKEVR         COPY TO 8 CHAR FIELD         BC10268 43268027
*  SEARCH IN TABL                                               BC10268 43269027
         LA    R4,JSTABLE          R4 -> TABL OF FOUND VARS    BC10268  43270027
JSSRCHLP DS    0H                                               BC10268 43280027
         CLC   JSTVAR,0(R4)        FOUND THE ENTRY ?            BC10268 43290027
         JE    JSCONV              YES- EXIT WITH RC=0          BC10268 43300027
         CLC   JSTEMPTY,0(R4)      EMPTY ENTRY FOUND ?          BC10268 43310027
         JE    JSNOCONV            NOT FOUND IN TABL            BC10268 43320027
         AHI   R4,L'JSTVAR         NEXT NETRY                   BC10268 43330027
         J     JSSRCHLP            CHECK NEXT                   BC10268 43340027
JSCONV   DS    0H                                               BC10268 43350027
         LHI   R15,0               PREPARE FOR RC=0             BC10268 43360027
         J     JSEXIT                                           BC10268 43370027
JSNOCONV DS    0H                                               BC10268 43380027
JSNOJSET DS    0H                                               BC10268 43390027
         LHI   R15,8               PREPARE FOR RC=8             BC10268 43400027
         J     JSEXIT                                           BC10268 43410027
JSEXIT   DS    0H                                               BC10268 43420027
         L     R11,JSLINCTR   RESTORE ADJUSTED LIN CNTR/POINTR BC10758  43430027
         L     R12,JSLINPTR   RESTORE ADJUSTED LIN CNTR/POINTR BC10758  43440027
         L     R1,4(0,R13)        INTO SAVE AREA               BC10758  43450027
         STM   R11,R12,64(R1)    (R0 IS AT OFFSET 20)          BC10758  43460027
         BRTRN (15)                                             BC10268 43470099
JSTAKEVR MVC   JSTVAR(*-*),0(R4)   FOR EX FROM CARD             BC10268 43470199
         DROP ,                                                 BC10273 43470299
*BC10918 SUBXRET                                               BC10918  43470399
*------------------------------------------------------------- BC10918  43471034
* SYMINST -                                                     BC10278 43577027
*                   IF JCL SYMBOL VARIABLE WAS SPECIFIED PER    BC10278 43578099
*BC10918 SUBXSET                                                BC10918 43578199
SYMINS   DS    0F                                               BC10918 43578299
         BEGIN SYMINS                 CYCLE, INSERT LIB\MEM\SYM BC10278 43579099
         L     R8,=A(CTMO15WS)                                  BC10918 43579199
         LAY   R5,4096(,R8)                                     BC10918 43579299
         USING CTMO15WS,R8,R5                                   BC10918 43579399
*BC10918 L     R8,=A(VARTAB)     ADDRESSABILITY ON DATA AREA    BC10278 43580063
*BC10918 USING VARTAB,R8                                        BC10278 43590063
         ST    R1,CHKAMPPA                                      BC10278 43600027
         L     R12,0(,R1)        TAKE FROM PARAMETER            BC10278 43610027
         L     R11,4(,R1)        TAKE FROM PARAMETER            BC10278 43620027
         ICM   R15,B'1111',IOABSRA  TREE WITH DATA WAS BUILT?   BC10278 43630027
         JNZ   SISEARCH          YES - SKIP INIT                BC10278 43640027
         LOAD  EP=IOABSR                                        BC10278 43650027
         ST    R0,IOABSRA                                       BC10278 43660027
* LOAD JCL VAR FILE INTO TREE                                   BC10278 43670027
         OPEN  (SIVARTAB)                                       BC10278 43680027
         GET   SIVARTAB             SKIP TITLE RECORD           BC10278 43690027
         GET   SIVARTAB             SKIP TITLE RECORD           BC10278 43700027
SIJVLP   DS    0H                                               BC10278 43710027
         GET   SIVARTAB                                         BC10278 43720027
         MVC   SIJVTJVR,0(R1)                                   BC10278 43730027
         MVC   SIJVTJV8,25(R1)                                  BC10278 43740027
         L     R15,IOABSRA                                      BC10278 43750027
         CALL  (15),(SIJVTREE,PUT,SIJVTKEY,SIJVTDAT)            BC10278 43760027
         LTR   R15,R15                                          BC10278 43770027
         BNZ   SIPERR                                           BC10278 43780027
         J     SIJVLP                                           BC10278 43790027
EOFJVAR  DS    0H                                               BC10278 43800027
         CLOSE (SIVARTAB)                                       BC10278 43810027
* LOAD APPL FILE INTO TREE                                      BC10278 43820027
         OPEN  (APPLFILE)                                       BC10278 43830027
         LA    R6,INREC                                         BC10278 43840099
         USING APLDSECT,R6         ESTABLISH ADDRESSABILITY     BC10278 43850099
SIAPLP   DS    0H                                               BC10278 43860027
         GET   APPLFILE,INREC                                   BC10278 43870027
SIAPLPAG DS    0H                                               BC10278 43880027
* IF RECTYPE=01 AND OPCJCLVAR IS NON-BALNK                      BC10278 43890027
* THEN ADD EN ENTRY WITH THE OPAPPLID, OPPERIOD, OPOFFSET       BC10278 43900027
*             VERIFY SAME OPAPPLID                              BC10278 43910027
* IF RECTYPE=03                                                 BC10278 43920027
* THEN SCAN ALL ENTRIES AND ADD A TREE-ENTRY WITH:              BC10278 43930027
*           OPJOBN, OPAPPLID, OPPERID, AN ITEM FROM OPOFFSET    BC10278 43940027
* ELSE CLEAR ENTRIES                                            BC10278 43950027
         CLC   RECTYPE,=C'01'                                   BC10278 43960027
         JE    SIADDAP                                          BC10278 43970027
         CLC   RECTYPE,=C'03'                                   BC10278 43980027
         JE    SIKEEPJB                                         BC10278 43990027
         J     SIAPLP                                           BC10278 44000027
SIADDAP  DS    0H                                               BC10278 44010027
         CLC   OPJCLVAR,=80C' '    IS THERE A JCL VAR FOR THIS? BC10278 44020027
         JE    SIAPNX                                           BC10278 44030027
         CLI   OPRUNTYP,C'-'       IS IT NEGATIVE RUN CYCLE?    BC10278 44040027
         JE    SIAPNX              YES - SKIP IT                BC10278 44050027
         CLI   OPRUNTYP,C'/'       IS IT NEGATIVE RUN CYCLE?    BC10278 44060027
         JE    SIAPNX              YES - SKIP IT                BC10278 44070027
         CLC   OPAPPLID,SICURRAP   IS IT IN THE SAME APPL?      BC10278 44080027
         JE    SIAASAME            YES - CONT TOP CHECK         BC10278 44090027
         MVC   SICURRAP,OPAPPLID   UPDATE CURRENT               BC10278 44100027
         XC    SIAPOFFN,SIAPOFFN   NO ENTRIES YET               BC10278 44110027
         MVC   SICURRAC,=A(SIAPOFFA) POINT TO 1ST               BC10278 44120027
SIAASAME DS    0H                                               BC10278 44130027
         L     R6,SIAPOFFN         R6 - NUM OF FILLED ENTRIES   BC10278 44140027
         AHI   R6,1                                             BC10278 44150027
         ST    R6,SIAPOFFN         R6 - NUM OF FILLED ENTRIES   BC10278 44160027
         L     R7,SICURRAC         R7 -> CURRENT ENTRY TO BE ADDBC10278 44170027
         USING SIAPOFF,R7                                       BC10278 44180027
         MVC   SIAOAPID,OPAPPLID                                BC10278 44190027
         MVC   SIAOPER,OPPERIOD                                 BC10278 44200027
         MVC   SIAO#SEQ,OP#SEQNO                                BC10278 44210027
         MVC   SIAOOFF,OPOFFSET                                 BC10278 44220027
         MVC   SIAOJVAR,OPJCLVAR                                BC10278 44230027
         AHI   R7,SIAPOFFL         TO NEXT ENTRY                BC10278 44240027
         ST    R7,SICURRAC         R7 -> CURRENT ENTRY TO BE ADDBC10278 44250027
SIAPNX   DS    0H                                               BC10278 44260027
         GET   APPLFILE,INREC      GET NEXT                     BC10278 44270027
         CLC   RECTYPE,=C'01'      STILL APPLICATION LINE       BC10278 44280027
         JE    SIADDAP             CONT TO PROCESS              BC10278 44290027
         J     SIAPLPAG            CONT WITH OTHER REC TYPES    BC10278 44300027
SIKEEPJB DS    0H                                               BC10278 44310027
         CLC   OPAPPLID,SICURRAP   SAME AS PREV PROCED APPL?    BC10278 44320027
         JNE   SIAPLP              NO - SKIP THIS JOB RECORD    BC10278 44330027
         CLC   OPJOBN,=80C' '      NON-EXECUTING JOB ?          BC10278 44340027
         JE    SIAPLP              YES - SKIP THIS JOB RECORD   BC10278 44350027
         L     R7,=A(SIAPOFFA)     R7 -> FIRST ENTRY            BC10278 44360027
         L     R6,SIAPOFFN         R6 - NUM OF ENTRIES          BC10278 44370027
SIKJLP   DS    0H                                               BC10278 44380027
         MVC   SIAPTJBN,OPJOBN      JOBNAME TO KEY              BC10278 44390027
         MVC   SIAPTAPP,SIAOAPID   APPL ID TO KEY               BC10278 44400027
         MVC   SIJVTJVR,SIAOJVAR   SET KEY FOR SEARCH           BC10278 44410027
         L     R15,IOABSRA                                      BC10278 44420027
         CALL  (15),(SIJVTREE,GET,SIJVTKEY,SIJVTDAT)            BC10278 44430027
         MVC   SIAPTJVR,SIJVTJV8   TRANSLATED JCL VAR TO KEY    BC10278 44440027
         MVC   SIAPTDD,=80C' '     START WITH BLANKS            BC10278 44450027
         MVC   SIAPTDD(L'SIAOPER),SIAOPER   BUILD THE RBC WITH  BC10278 44460027
         L     R14,=A(BLANK)   GET LENGTH OF NAME               BC10278 44470027
         TRT   SIAPTDD,0(R14)      R1 -> FIRST BLANK            BC10278 44480027
         MVI   0(R1),C'_'          ADD _ AFTER PERIOD           BC10278 44490027
         XR    R9,R9               CLEAR R9                     BC10278 44500027
         IC    R9,SIAO#SEQ         GET SEQ NUMBER               BC10278 44510027
         CVD   R9,WORK                                          BC10278 44520027
         UNPK  1(2,R1),WORK        MAKE NUMERIC                 BC10278 44530027
         OI    2(R1),X'F0'         MAKE PRINTABLE               BC10278 44540027
         AHI   R1,3                R1 -> AFTER THE SEQ NUM      BC10278 44550027
         LA    R3,SIAOOFF          R3 -> FIRST OFFSET           BC10278 44560027
         CLC   4(4,R3),=80C' '     IS IT ONLY ENTRY ?           BC10278 44570027
         JE    SIKJKEEP            YES - JUST KEEP              BC10278 44580027
SIKJPROC DS    0H                                               BC10278 44590027
         CLC   0(4,R3),=C'+001'    IS IT OFFSET OF 1?           BC10278 44600027
         JE    SIKJKEEP            YES - JUST KEEP              BC10278 44610027
         MVI   0(R1),C'_'          ADD _ AFTER SEQ#             BC10278 44620027
         MVC   1(4,R1),0(R3)       ADD THE OFFSET               BC10278 44630027
SIKJKEEP DS    0H                                               BC10278 44640027
         ST    R1,SAVER1                                        BC10278 44650027
         L     R15,IOABSRA                                      BC10278 44660027
         CALL  (15),(SIAPTREE,PUT,SIAPTKEY,SIAPTDAT)            BC10278 44670027
         LTR   R15,R15                                          BC10278 44680027
         BNZ   SIPERR                                           BC10278 44690027
         L     R1,SAVER1                                        BC10278 44700027
         MVC   0(5,R1),=80C' '     CLEAR OFFSET IN RBC          BC10278 44710027
         AHI   R3,4                R3-> NEXT OFFSET             BC10278 44720027
         CLC   0(4,R3),=80C' '     IS ENTRY BLANKS ?            BC10278 44730027
         JNE   SIKJPROC            NO - PROCESS IT              BC10278 44740027
         AHI   R7,SIAPOFFL         TO NEXT ENTRY                BC10278 44750027
         BCT   R6,SIKJLP           PROCESS IT                   BC10278 44760027
         J     SIAPLP              YES - GET NEXT REC FOR PROC  BC10278 44770027
EOFAPPL  DS    0H                                               BC10278 44780027
         CLOSE (APPLFILE)                                       BC10278 44790027
         DROP  R6                                               BC10278 44800099
SISEARCH DS    0H                  SEARCH FOR MEMBR IN TABLES  BC10278  44810027
         XC    SIAPTKS(SIAPTKL),SIAPTKS  CLERA KEY              BC10278 44820027
         MVC   SIAPTJBN,MEMBER     USE MEMBR AS THE KEY        BC10278  44830027
         MVC   SICURRAP,=80C' '    CLEAR WITH BLANKS            BC10278 44840027
SISENX   DS    0H                                               BC10278 44850027
         L     R15,IOABSRA                                      BC10278 44860027
         CALL  (15),(SIAPTREE,NEXT,SIAPTKEY,SIAPTDAT)           BC10278 44870027
         LTR   R15,R15           NEXT KEY FOUND ?               BC10278 44880027
         JNZ   SICLSJOB          NO - END - SKIP JOB AND CONT   BC10278 44890027
         CLC   SIAPTJBN,MEMBER   IS THERE A RECORD FOR THIS JOB?BC10278 44900027
         JNE   SICLSJOB          NO - JUST CONT                 BC10278 44910027
         OI    FLAGS,CHANGES                                    BC10278 44920027
         AHI   R12,-80    ONE CARD BACK TO INSERT BEFORE FIRST  BC10278 44930027
         CLC   SICURRAP,SIAPTAPP  STILL IN THE SAME APPL?       BC10278 44940027
         JE    SIADELSE         YES - ADD ELSE / NO ADD IF APPL BC10278 44950027
         LHI   R7,0               CLEAR REG                     BC10278 44960027
         ICM   R7,B'0011',SIEIFCNT GET THE NUMEBR OF PENDING IF BC10278 44970027
         JZ    SIADIFAP           NONE - JUST ADD IF            BC10278 44980027
SIAENLP  DS    0H                                               BC10278 44990027
         LA    R12,80(,R12)        POINT TO NEXT CARD           BC10278 45000027
         LARL  R9,INSERT                                        BC10278 45010027
         BALR  R9,R9                                            BC10278 45020027
         MVC   80(80,R12),0(R12)                                BC10278 45030027
         MVC   0(80,R12),=80C' '                                BC10278 45040027
         MVC   0(L'SIENDIF,R12),SIENDIF                         BC10278 45050027
         BCT   R7,SIAENLP         LOOP FOR ALL REQUIRED ENDIF   BC10278 45060027
         MVC   SIEIFCNT,=H'0'     START WITH 0 FOR THE IF APPL  BC10278 45070027
SIADIFAP DS    0H                                               BC10278 45080027
         LH    R9,SIEIFCNT                                      BC10278 45090027
         AHI   R9,1                                             BC10278 45100027
         STH   R9,SIEIFCNT                                      BC10278 45110027
         MVC   SICURRAP,SIAPTAPP  KEEP FOR NEXT ROUND           BC10278 45120027
         MVC   SIIFANAM,SIAPTAPP  PUT IN IF                     BC10278 45130027
         LA    R12,80(,R12)        POINT TO NEXT CARD           BC10278 45140027
         LARL  R9,INSERT                                        BC10278 45150027
         BALR  R9,R9                                            BC10278 45160027
         MVC   80(80,R12),0(R12)                                BC10278 45170027
         MVC   0(80,R12),=80C' '                                BC10278 45180027
         MVC   0(L'SIIFAPPL+L'SIIFANAM,R12),SIIFAPPL            BC10278 45190027
         J     SIADDIFR         CONT TO ADD IF RBC              BC10278 45200027
SIADELSE DS    0H                                               BC10278 45210027
         LA    R12,80(,R12)        POINT TO NEXT CARD           BC10278 45220027
         LARL  R9,INSERT                                        BC10278 45230027
         BALR  R9,R9                                            BC10278 45240027
         MVC   80(80,R12),0(R12)                                BC10278 45250027
         MVC   0(80,R12),=80C' '                                BC10278 45260027
         MVC   0(L'SIELSE,R12),SIELSE                           BC10278 45270027
SIADDIFR DS    0H                                               BC10278 45280027
         LH    R9,SIEIFCNT                                      BC10278 45290027
         AHI   R9,1                                             BC10278 45300027
         STH   R9,SIEIFCNT                                      BC10278 45310027
         MVC   SIIFRNAM,SIAPTDD   PUT RBC NAME IN IF            BC10278 45320027
         LA    R12,80(,R12)        POINT TO NEXT CARD           BC10278 45330027
         LARL  R9,INSERT                                        BC10278 45340027
         BALR  R9,R9                                            BC10278 45350027
         MVC   80(80,R12),0(R12)                                BC10278 45360027
         MVC   0(80,R12),=80C' '                                BC10278 45370027
         MVC   0(L'SIIFRBC+L'SIIFRNAM,R12),SIIFRBC              BC10278 45380027
         LA    R12,80(,R12)        POINT TO NEXT CARD           BC10278 45390027
         LARL  R9,INSERT                                        BC10278 45400027
         BALR  R9,R9                                            BC10278 45410027
         MVC   80(80,R12),0(R12)                                BC10278 45420027
         MVC   0(80,R12),=80C' '                                BC10278 45430027
         MVC   0(L'MYLIBSYM+L'MYLIBNAM,R12),MYLIBSYM            BC10278 45440027
         LA    R12,80(,R12)        POINT TO NEXT CARD           BC10278 45450027
         LARL  R9,INSERT                                        BC10278 45460027
         BALR  R9,R9                                            BC10278 45470027
         MVC   80(80,R12),0(R12)                                BC10278 45480027
         MVC   0(80,R12),=80C' '                                BC10278 45490027
*BC10370 MVC   MYMEMNAM,SIAPTJVR                                BC10278 45500027
*BC10370 MVC   0(L'MYMEMSYM+L'MYMEMNAM,R12),MYMEMSYM            BC10278 45510027
         MVC   MYMEMNAM(L'SIAPTJVR),SIAPTJVR            BC10278 BC10370 45520027
         MVC   0(L'MYMEMSYM+L'SIAPTJVR,R12),MYMEMSYM    BC10278 BC10370 45530027
         LA    R12,80(,R12)        POINT TO NEXT CARD           BC10278 45540027
         LARL  R9,INSERT                                        BC10278 45550027
         BALR  R9,R9                                            BC10278 45560027
         MVC   80(80,R12),0(R12)                                BC10278 45570027
         MVC   0(80,R12),=80C' '                                BC10278 45580027
         MVC   0(L'LIBSYM,R12),LIBSYM NOW COPY THE LINE ITSELF  BC10278 45590027
         LA    R12,80(,R12)        POINT AFTER IT               BC10278 45600027
         J     SISENX          GET NEXT ENTRY FOR THE JOB       BC10278 45610027
SICLSJOB DS    0H                                               BC10278 45620027
         LHI   R7,0               CLEAR REG                     BC10278 45630027
         ICM   R7,B'0011',SIEIFCNT GET THE NUMEBR OF PENDING IF BC10278 45640027
         JZ    SIOK               NONE - JUST EXIT              BC10278 45650027
         AHI   R12,-80                                          BC10278 45660027
SIAENLPC DS    0H                                               BC10278 45670027
         LA    R12,80(,R12)        POINT TO NEXT CARD           BC10278 45680027
         LARL  R9,INSERT                                        BC10278 45690027
         BALR  R9,R9                                            BC10278 45700027
         MVC   80(80,R12),0(R12)                                BC10278 45710027
         MVC   0(80,R12),=80C' '                                BC10278 45720027
         MVC   0(L'SIENDIF,R12),SIENDIF                         BC10278 45730027
         BCT   R7,SIAENLPC        LOOP FOR ALL REQUIRED ENDIF   BC10278 45740027
         STCM  R7,B'0011',SIEIFCNT  UPDATE TO 0 FOR NEXT JOB    BC10278 45750027
*BC10294 AHI   R12,-80                                          BC10278 45760027
         AHI   R12,80   POINT R12 BACK TO THE FIRST JCL CARD    BC10294 45770027
SIOK     DS    0H                                               BC10278 45780027
         LHI   R15,0                                            BC10278 45790027
         J     SIPRTR                                           BC10278 45800027
SIPERR   DS    0H                                               BC10278 45810027
         WTO   'SIPERR'                                         BC10278 45820027
         LHI   R15,8                 SIGN ERROR IN CARD         BC10278 45830027
SIPRTR   DS    0H                                               BC10278 45840027
         L     R1,CHKAMPPA                                      BC10278 45850027
         ST    R12,0(,R1)  UPDATE PARAMETER TO BE USED BY CALLERBC10278 45860027
         ST    R11,4(,R1)  UPDATE PARAMETER TO BE USED BY CALLERBC10278 45870027
         BRTRN (15)                                             BC10278 45880099
*BC10918 SUBXRET                                                BC10918 45890099
*                                                               BC10327 45970027
         DROP  ,                                                BC10327 45980099
*-------------------------------------------------------------  BC10918 45981034
*BC10918 SUBXSET                                                BC10918 45990099
FJOBAPPL DS    0F                                               BC10918 45991099
         BEGIN FJOBAPPL               get application of a job  BC10327 46000099
         L     R8,=A(CTMO15WS)                                  BC10918 46001099
         LAY   R5,4096(,R8)                                     BC10918 46003099
         USING CTMO15WS,R8,R5                                   BC10918 46004099
         L     R2,=A(JOBSTART)                                  BC10327 46010027
         L     R1,0(R2)               R1 -> XRF AREA            BC10327 46020027
         L     R2,=A(JOBEND)                                    BC10327 46030027
         L     R3,0(R2)               R3 -> END OF XRF AREA     BC10327 46040027
         USING JOBDSECT,R1                                      BC10327 46050027
         L     R2,=A(JOBNAM)          R2 -> CURRENT JOB NAME    BC10327 46060027
SKIPJA1  DS    0H                                               BC10327 46070027
         CLC   INJOBNAM,0(R2)         JOB NAME FOUND?           BC10327 46080027
         JNE   SKIPJA2                IF NO - SKIP.             BC10327 46090027
         L     R2,=A(APPLWORK)        R2 -> CURRENT APPLICATION BC10327 46100027
         MVC   0(L'APPLWORK,R2),INJOBAPL KEEP APPL NAME OF JOB  BC10327 46110027
         B     SKIPJAX                                          BC10327 46120027
SKIPJA2  DS    0H                                               BC10327 46130027
         LA    R1,INJOBL(R1)          NEXT ENTRY IN MEMORY      BC10327 46140027
         CR    R1,R3                  TABL END ?               BC10327  46150027
         JL    SKIPJA1                IF NO - SKIP              BC10327 46160027
SKIPJAX  DS    0H                                               BC10327 46170027
         BRTRN 0                                                BC10918 46180099
         DROP  ,                                                BC10327 46190099
*-------------------------------------------------------------  BC10918 46210034
*BC10918 SUBXSET                                               BC10918  46220099
INIT     DS    0F                                               BC10918 46220199
         BEGIN INIT                                            BC10370  46221099
         L     R8,=A(CTMO15WS)                                  BC10918 46222099
         LAY   R5,4096(,R8)                                     BC10918 46222199
         USING CTMO15WS,R8,R5                                   BC10918 46222299
*BC10918 L     R8,=A(VARTAB)     ADDRESSABILITY ON DATA AREA   BC10370  46230063
*BC10918 USING VARTAB,R8                                       BC10370  46240063
         L     R15,=A(GETVARS)                                  WC10076 46250027
         BASR  R14,R15                                          WC10076 46260027
*  BUILD TR TABL  BASED OV TRANSR VARIABLE                      WC10083 46270027
         L     R15,=A(TRITSELF)       GET ADDR                  BC10268 46280027
         L     R14,=A(TRTRANS)                                  BC10351 46290027
*BC10268 MVC   TRTRANS,TRITSELF       PUT TABEL BASE VALUE      WC10083 46300027
*BC10351 MVC   TRTRANS,0(R15)         PUT TABEL BASE VALUE      BC10268 46310027
         MVC   0(L'TRTRANS,R14),0(R15)  PUT TBL BASE VALUE      BC10351 46320027
         LA    R15,TRANSR             TAKE TRANS SPEC           WC10083 46330027
QSRLOOP  DS    0H                                               WC10083 46340027
         CLI   0(R15),C' '            MORE CHARS ?              WC10083 46350027
         BE    QSRDO                  NO - TRANSFORM            WC10083 46360027
         XR    R2,R2                  ZERO FOR ICM              WC10083 46370027
         ICM   R2,B'0001',0(R15)  TAKE THE FIRST CHAR IN PAIR   WC10083 46380027
         A     R2,=A(TRTRANS)         POINT TO CHAR IN TR TABL  WC10083 46390027
         MVC   0(1,R2),1(R15)         REPLACE WITH THE 2ND      WC10083 46400027
         AHI   R15,2                  R15 -> NEXT PAIR          WC10083 46410027
         B     QSRLOOP                CONT                      WC10083 46420027
QSRDO    DS    0H                                               WC10083 46430027
         L     R0,RESMAX                                        WC10076 46440027
         MH    R0,=Y(LRESTBL)     CALCULATE TABL SIZE          WC10076  46450027
         GETMAIN RU,LV=(0),LOC=RES                              WC10076 46460027
         ST    R1,RESTBL          SAVE IT                       WC10076 46470027
         LHI   R0,100             MAX NUMBWER OF DIFFERENT CAL  BC10327 46480027
         MHI   R0,16+8            CALCULATE TABL SIZE          BC10327  46490034
         GETMAIN RU,LV=(0),LOC=RES                              BC10327 46500027
         ST    R1,CALSTART        SAVE IT                       BC10327 46510027
         LR    R3,R1              R3 -> AREA FOR CAL NAMES      BC10327 46520027
         L     R2,=A(CALNAMES)    R2 -> DCB OF CAL.NAMES        BC10327 46530027
         OPEN  ((R2))             OPEN                          BC10327 46540027
CALTBLBL DS    0H                 LOOP ON ALL FILE RECORDS      BC10327 46550027
         GET   (R2)               NEXRT REC                     BC10327 46560027
         CLI   PERIOD-CALDSECT(R1),C' ' FIRST ENTRY (NO PERIOD)?BC10327 46570027
         JNE   CALTBLBL           NO - JUST CONT LOOP           BC10327 46580027
         MVC   0(16,R3),OLDCAL-CALDSECT(R1) ORIGINAL CAL NAME   BC10327 46590027
         MVC   16(8,R3),NEWCAL-CALDSECT(R1)                     BC10327 46600027
         AHI   R3,24                 R3 -> NEXT ENTRY           BC10327 46610027
         J     CALTBLBL            CONT TO NEXT                 BC10327 46620027
CALEOD   DS    0H                                               BC10327 46630027
         ST    R3,CALEND                                        BC10327 46640027
         CLOSE ((R2))                                           BC10327 46650027
         L     R2,=A(CHGFILE)                                   WC0237  46660027
         L     R3,=A(RESNAME)                                   WC0237  46670027
         L     R4,=A(DABATCH)                                   WC0237  46680027
         L     R7,=A(XRFFILE)                                 WC10026   46690027
         OPEN  ((R2),,(R3),,(R4),,(R7))    DONT USE R5!       WC10026   46700027
         LOAD  EP=CTMCDPRC  RTN TO FILL INSTREAM PROC VARS TBL BC10064  46710027
         ST    R0,CAS51PRC                                     BC10064  46720027
         L     R3,APPLMAX        GET COUNT OF APPLS             WC10076 46730027
         MHI   R3,CHGFILEN         ENTRY LENGTH=32     WC10075 BC10360  46740027
         GETMAIN RU,LV=(R3),LOC=ANY STRG FOR APPL NEW-NAMES FILEWC10075 46750027
         ST    R1,CHGSTART         CHANGE START ADDRESS         WC0096  46760027
         LR    R3,R1                                            WC0096  46770027
CHGLOOP  L     R1,=A(CHGFILE)                                   WC0237  46780027
         GET   (R1)             READ APPL NEW-NAMES REC         WC0237  46790027
         MVC   0(16,R3),0(R1)      GET OLD-APPL-NAME            WC0096  46800027
         MVC   16(8,R3),17(R1)     APPLICATION NEW NAME         WC0096  46810027
         L     R15,CALSTART        R15 -> CAL NAMES TABL        BC10327 46820027
CALTBLSL DS    0H                  LOOP TO FIND NEW CAL NAME    BC10327 46830027
         CLC   0(16,R15),105(R1)   IS THIS THE ENTRY?           BC10327 46840027
         JE    CALTBLFN            YES - CONT AND USE           BC10327 46850027
         AHI   R15,16+8            NEXT ENTRY                   BC10327 46860027
         C     R15,CALEND          END OF AREA?                 BC10327 46870027
         JL    CALTBLSL            NO - CONT LOOPING            BC10327 46880027
         L     R15,=A(CALENDAR-16) NOT FOUND - POINT TO DEFAULT BC10327 46890027
CALTBLFN DS    0H                                               BC10327 46900027
         MVC   24(8,R3),16(R15)    COPY THE CAL NEW NAME TO APPLBC10327 46910027
*BC10360 LA    R3,32(R3)           NEXT ENTRY IN MEMORY         BC10327 46920027
         LA    R3,CHGFILEN(R3)    NXT ENTRY IN MEMORY   BC10327 BC10360 46930027
         B     CHGLOOP                                          WC0096  46940027
EOFCHG   EQU   *                                                WC0096  46950027
         ST    R3,CHGEND           CHANGE END-ADDR              WC0096  46960027
         MVC   CALENDAR,=80C' '    INIT TO BLANKS               BC10327 46970027
*WC10076 L     R3,LOADJOB#         GET COUNT OF JOB            WC10012  46980027
         L     R3,JOBMAX           GET COUNT OF JOB             WC10076 46990027
         MH    R3,=AL2(INJOBL)     ENTRY LENGTH                WC10012  47000027
         GETMAIN RU,LV=(R3),LOC=ANY AREA FOR XRF TABL          WC10012  47010027
         ST    R1,JOBSTART         CHANGE START ADDRESS        WC10012  47020027
         AR    R1,R3                                           WC10012  47030027
         ST    R1,JOBEND           GETMAIN END ADDRESS         WC10012  47040027
         L     R3,JOBSTART                                     WC10012  47050027
JOBLOOP  L     R1,=A(XRFFILE)      READ NEW NAMES RECORD       WC10012  47060027
         GET   (R1),LINE           READ NEW NAMES RECORD       WC10012  47070027
         MVC   0(INJOBL,R3),LINE   APPL/OPER/JOBNAME           WC10012  47080027
         LA    R3,INJOBL(R3)       NEXT ENTRY IN MEMORY        WC10012  47090027
         B     JOBLOOP                                         WC10012  47100027
EOFJOB   EQU   *                                               WC10012  47110027
         ST    R3,JOBEND           JOB    END-ADDR             WC10012  47120027
         L     R3,=A(BATTBL)       LOAD THE PGM/PROC TABL       WC0225  47130027
         LA    R2,10              MAX NUMBER                    WC0225  47140027
BATLOOP  L     R1,=A(DABATCH)                            WC0225 WC0237  47150027
         GET   (R1)                LOAD THE OPC PGM/PROC NAMES  WC0237  47160027
         MVC   1(L'BATTBL,R3),0(R1) SAVE PGM/PROC               WC0225  47170027
         LR    R15,R1               BEGIN ADDR OF PGM/PROC      WC0225  47180027
*WC10012 TRT   0(9,R1),BLANK         GET LENGTH OF NAME         WC0225  47190027
         L     R14,=A(BLANK)   GET LENGTH OF NAME       WC0225 WC10012  47200027
         TRT   0(9,R1),0(R14)                           WC0225 WC10012  47210027
         BZ    BATLOOP               INVALID ENTRY              WC0225  47220027
         SR    R1,R15                                           WC0225  47230027
         BZ    BATLOOP              BLNK ENTRY                 WC0225   47240027
         BCTR  R1,0                                             WC0225  47250027
         STC   R1,0(R3)             SAVE THE LENGTH             WC0225  47260027
         LA    R3,L'BATTBL(,R3)                                 WC0225  47270027
         BCT   R2,BATLOOP                                       WC0225  47280027
EOFBAT   DS    0H                                               WC10076 47290027
         L     R3,RESTBL              LOAD THE RESOURCE TABL    WC10076 47300027
RESGET   L     R1,=A(RESNAME)                            WC0221 WC0237  47310027
         GET   (R1)                                             WC0237  47320027
         MVC   0(LRESTBL,R3),0(R1)                              WC10076 47330027
         LA    R3,LRESTBL(,R3)                                  WC10076 47340027
         B     RESGET                                           WC0221  47350027
EOFRES   EQU   *                                                WC0225  47360027
         MVI   0(R3),C' '         clear last entry              WC10076 47370027
         MVC   1(LRESTBL-1,R3),0(R3)                            WC10076 47380027
         GETMAIN RC,LV=8000        ROOM FOR 100 SYSIN CARDS     WC0225  47390027
         ST    R1,ASYSIN           ADDR OF SYSIN MEMBR         WC0225   47400027
         L     R2,=A(CHGFILE)                                   WC0237  47410027
         L     R3,=A(RESNAME)                                   WC0237  47420027
         L     R4,=A(DABATCH)                                   WC0237  47430027
         L     R7,=A(XRFFILE)                                 WC10026   47440027
         CLOSE ((R2),,(R3),,(R4),,(R7))                       WC10026   47450027
         L     R2,ERROR            ADDRESS OF ERROR ROUTINE     BC10273 47460027
         CALL  CTMOP018,(ACTMMEM,MCTADDR,(R2),VARNMTBL,         BC10276*47470027
               VARTABBF,VARTABEN)     VARTAB START/END          BC10276 47480027
         LTR   R15,R15             LIBSYM BUILT OK?             BC10276 47490027
*BC10370 BNZ   RETURN              NO - ABRT EXECUTION         BC10276  47500027
         BNZ   ABORT               NO - ABRT EXECUTION         BC10370  47510027
         L     R2,=A(LIBSYMDD)     LIBSYM DCB                    WC0083 47520027
         RDJFCB ((R2))             GET DSN FROM JFCB             WC0083 47530027
         L     R1,=A(LIBSYMDS)     MOVE DSN TO %%LIBSYM STMT     WC0083 47540027
         MVC   MYLIBNAM,0(R1)                                   BC10276 47550027
         L     R2,=A(CASECODE)                                   WC0225 47560027
         L     R3,=A(NOERROR)                                    WC0225 47570027
         L     R4,=A(RECVEXT)                                    WC0225 47580027
         OPEN  ((R2),,(R3),,(R4),(OUTPUT))                       WC0225 47590027
         LTR   R15,R15                                           WC0001 47600027
         BNZ   NOCASES                                           WC0001 47610027
         LA    R9,NOCASES     SET RETURN ADDR IN CASE OF ERROR   WC0001 47620027
         ST    R9,SAVER9                                         WC0001 47630027
         L     R7,=A(CASETBL)  LOAD CASE TABL             WC0001 BC0101 47640027
         LA    R3,20       MAX 20 CASE ENTRIES                   WC0001 47650027
CASELP1  LA    R4,11       MAX 10 CODES PER CASE                 WC0001 47660027
         L     R1,=A(CASECODE)                                   WC0225 47670027
         GET   (R1)                                       WC0001 WC0225 47680027
         LR    R12,R1                                            WC0001 47690027
         ST    R1,CURRADDR                                       WC0001 47700027
CASELP2  TRT   0(6,R12),PARCOMA    FIND NEXT  BLNK OR COMMA     WC0001  47710027
*BC10370 BZ    OPCERR                                            WC0001 47720027
         BZ    INITERR                                 WC0001 BC10370   47730027
         LR    R15,R1              SAVE ADDR                     WC0001 47740027
         SR    R1,R12              GET LENGTH                    WC0001 47750027
         BZ    NOMOCASE            NO MORE CODES                 WC0001 47760027
         BCTR  R1,0                                              WC0001 47770027
         EX    R1,CASEMVC          MOVE THE CASE CODE IN         WC0001 47780027
         L     R1,CURRADDR                                       WC0001 47790027
         LA    R1,71(,R1)         POINT TO END OF LINE          WC0001  47800027
         SR    R1,R15              LENGTH OF REMAINING LINE      WC0001 47810027
         L     R14,=A(NONBLANK)                                 BC10758 47820027
         EX    R1,CASETRT          FIND NEXT NON-BLNK           WC0001  47830027
         BZ    CASEBLNK            NO MORE CASES                 WC0001 47840027
         LR    R12,R1                                            WC0001 47850027
NOMOCASE LA    R7,5(,R7)           POINT TO NEXT CODE IN TBL     WC0001 47860027
         BCT   R4,CASELP2             - GET A NEXT CODE          WC0001 47870027
CASENXT  BCT   R3,CASELP1             - GET A NEW CASE REC       WC0001 47880027
         WTO   'CTMOP015-01E MAXIMUM NUMBER OF CASE CODES EXCEEDED'     47890027
ABORT    EQU   *                                                BC10370 47900027
         LA    R15,8                                      WC0001 WC0367 47910027
*BC10370 B     RETURN                                     WC0001 WC0367 47920027
         B     INITRET       RET W/ RC=8 ABORT   WC0001 WC0367 BC10370  47930027
CASEBLNK LA    R7,5(,R7)                                         WC0001 47940027
         BCT   R4,CASEBLNK                                       WC0001 47950027
         B     CASENXT                                           WC0001 47960027
CASEMVC  MVC   0(*-*,R7),0(R12)    MOVE IN CASE ENTRY            WC0001 47970027
*CASETRT  TRT   0(*-*,R15),NONBLANK FIND NEXT NON-BLNK           WC0001 47980027
CASETRT  TRT   0(*-*,R15),0(R14)   FIND NEXT NON-BLNK           WC0001  47990027
*                                                                WC0001 48000027
NOCASES  DS    0H                                               BC10327 48010027
         SR    R15,R15                                          BC10370 48020027
INITRET  DS    0H      R15=4 MEANS OPCERR; R15=8 MEANS RETURN   BC10370 48030052
         BRTRN (15)    R15=4 MEANS OPCERR; R15=8 MEANS RETURN   BC10370 48031099
*BC10918 SUBXRET                       |Exit subrt-unwind SA    BC10370 48032099
INITERR  LA    R15,4     INDICATE BR TO OPCERR                  BC10370 48040027
         B     INITRET                                          BC10370 48050027
         DROP  ,                                                BC10327 48050199
*-------------------------------------------------------------  BC10918 48051034
CONSTS   LOCTR ,                       |                       BC10906  48051199
CTMO15WS DS    0D                                              BC10918  48051299
         LTORG                         |                       BC10906  48051399
WSDATA   LOCTR ,                       |                       BC10906  48051499
SIAPOFFN DC    A(0)               NUMBER OF FILLED ENTRIES      BC10278 48070027
SICURRAC DC    A(SIAPOFFA)        PTR TO CURRENT ENTRY          BC10278 48080027
SICURRAP DC    CL(L'OPAPPLID)' '  CURRENT APPLICATION BEING PROCBC10278 48090027
SIJVTREE DC    16A(0)                                           BC10278 48100027
SIJVTKEY DC    Y(SIJVTKL)                                       BC10278 48110027
SIJVTKS  EQU   *                                                BC10278 48120027
SIJVTJVR DC    CL(L'OPJCLVAR)' '                                BC10278 48130027
SIJVTKL  EQU   *-SIJVTKS                                        BC10278 48140027
SIJVTDAT DC    Y(SIJVTDL)                                       BC10278 48150027
SIJVTDS  EQU   *                                                BC10278 48160027
SIJVTJV8 DC    CL8' '                                           BC10278 48170027
SIJVTDL  EQU   *-SIJVTDS                                        BC10278 48180027
SIAPTREE DC    16A(0)                                           BC10278 48190027
SIAPTKEY DC    Y(SIAPTKL)                                       BC10278 48200027
SIAPTKS  EQU   *                                                BC10278 48210027
SIAPTJBN DC    CL(L'OPJOBN)' '                                  BC10278 48220027
SIAPTAPP DC    CL(L'OPAPPLID)' '                                BC10278 48230027
SIAPTJVR DC    CL(L'SIJVTJV8)' '                                BC10278 48240027
SIAPTDD  DC    CL16' '                                          BC10278 48250027
SIAPTKL  EQU   *-SIAPTKS                                        BC10278 48260027
SIAPTDAT DC    Y(SIAPTDL)                                       BC10278 48270027
SIAPTDS  EQU   *                                                BC10278 48280027
SIAPTDL  EQU   *-SIAPTDS                                        BC10278 48290027
SIEIFCNT DC    H'0'             COUNTR OF EXPECTED %%ENDIF      BC10278 48300027
*SIIFAPPL DC    C'//* %%IF %%APPL=' CHECK FOR APPL      BC10278 BC10283 48310027
SIIFAPPL DC    C'//* %%IF %%APPL EQ ' CHECK FOR APPL            BC10283 48320027
SIIFANAM DC    CL16' '           THIS MUST FOLLOW SIIFAPPL      BC10278 48330027
*SIIFRBC  DC    C'//* %%IF %%$RBC=' CHECK FOR RBC     BC10278   BC10283 48340027
SIIFRBC  DC    C'//* %%IF %%$RBC EQ ' CHECK FOR RBC             BC10283 48350027
SIIFRNAM DC    CL(L'SIAPTDD)' '  THIS MUST FOLLOW SIIFRBC       BC10278 48360027
SIELSE   DC    C'//* %%ELSE'       SWITCH IF                    BC10278 48370027
SIENDIF  DC    C'//* %%ENDIF'      CLOSE IF                     BC10278 48380027
IOABSRA  DC    A(0)              ADDRESS OF LOADED IOABSR       BC10278 48390027
PUT      DC    CL4'PUT '                                        BC10278 48400027
GET      DC    CL4'GET '                                        BC10278 48410027
NEXT     DC    CL4'NEXT'                                        BC10278 48420027
JSVARPOS DS    A                   POS OF VAR ON LINE           BC10450 48421034
JSLINPTR DS    A                   CURRENT LINE PTR             BC10450 48422034
JSLINCTR DS    A                   CURRENT LINE COUNTER        BC10758  48423034
VALDELIM DS    A          POS OF VAR VALUE DELIM               BC10456  48424034
ERROR1   DS    A          USED TO LOAD DCB'S ADDR OF ERROR MSG BC10893  48425034
JSTVAR   DC    CL8' '              PLACE FOR HOLDING THE VAR    BC10268 48426034
JSTEMPTY DC    CL(L'JSTVAR)' '     EMPTY ENTRY                  BC10268 48427034
LONGSET  DC    CL1'N'   FLAG FOR SET VARIABLE UNRESOLVED        BC10469 48429034
* ADDING '-' BEFORE THE MSGID                                  BC10894  48429134
                                                                        48429234
ERROR004 DC    CL133' '                                        BC10893  48429334
         ORG   ERROR004                                        BC10893  48429434
         DC    CL16'-CTMOP015-01E - '                          BC10893  48429534
ERR04MEM DS    CL8                                             BC10893  48429634
         DC    CL1' '                                          BC10893  48429734
ERR04DES DS    CL108                                           BC10893  48429834
                                                                        48429934
ERROR005 DC    CL133' '                                        BC10893  48430034
         ORG   ERROR005                                        BC10893  48430134
         DC    CL16'-CTMOP015-00E - '                          BC10893  48430234
         DC    CL5'JOB= '                                      BC10893  48430334
ERR05MEM DS    CL8                                             BC10893  48430434
         DC    CL25', OPC BATCH      COMMAND '                 BC10893  48430534
ERR05CMD DS    CL7                                             BC10893  48430634
         DC    CL72' COULD NOT BE CONVERTED, RC=XX'            BC10893  48430734
                                                                        48430834
ERROR001 DC    CL133' '                                        BC10893  48430934
         ORG   ERROR001                                        BC10893  48431034
         DC    CL16'-CTMOP015-07W - '                          BC10893  48431134
ERR01MEM DS    CL8                                             BC10893  48431234
         DC    CL1' '                                          BC10894  48431334
ERR01VAR DS    CL16                                            BC10893  48431434
         DC    CL92' MEMSYM NAME MAY NOT EXIST OR MAY BE INCORRECTLY RE*48431534
               SOLVED AT RUNTIME'                              BC10893  48431634
                                                                        48431734
ERROR002 DC    CL133' '                                        BC10893  48431834
         ORG   ERROR002                                        BC10893  48431934
         DC    CL16'-CTMOP015-03W - '                          BC10893  48432034
ERR02MEM DS    CL8                                             BC10893  48432134
         DC    CL9' RESNAME='                                  BC10893  48432234
ERR02RES DS    CL20                                            BC10893  48432334
         DC    CL80' DOES NOT EXIST IN OPC DATABASE'           BC10893  48432434
                                                                        48432534
VARTAB   DS    0F                                               WC10076 48432634
*        Types of Variables                                           * 48432734
*        CTMCDFVR variable,type,length                                * 48432834
*        C    - character                                             * 48432934
*        N    - numeric                                               * 48433034
*        L    - character preceded by two bytes binary actual length  * 48433134
         PRINT GEN                                                      48433234
*        DEFINE VARIABLE AREA                                           48433334
         CTMCDFVR APPLMAX,N,4                                   WC10076 48433434
VARENTL  EQU   *-VARTAB                                         WC10076 48433534
         CTMCDFVR JOBMAX,N,4                                    WC10076 48433634
         CTMCDFVR RESMAX,N,4                                    WC10076 48433734
         CTMCDFVR VER,C,1                                       WC10076 48433834
         CTMCDFVR CTR,C,1                                       WC10076 48433934
         CTMCDFVR PNIBTSD,C,1                                   WC10076 48434034
         CTMCDFVR AUTSCAN,C,1                                   WC10076 48434134
         CTMCDFVR RETCODE,C,8                                   WC10076 48434234
         CTMCDFVR GTABLE,C,8                                    WC10076 48434334
*BC10370 CTMCDFVR PRODUCT,C,8                                   WC10076 48434434
*BC10371 CTMCDFVR TRANSR,C,16,'|.*X'                            WC10083 48434534
         CTMCDFVR TRANSR,C,16,'|!*X({)},;' ADD MORE DFLTSWC10083BC10371 48434634
*BC10327 CTMCDFVR CALENDAR,C,8                                  BC10268 48434734
         CTMCDFVR SHIFTEND,C,1,'Y'                              BC10314 48434834
NUMVAR   EQU   (*-VARTAB)/VARENTL                               WC10076 48434934
VARVALS  DS    0F                                               WC10076 48435034
         CTMCDFVR ,                                             WC10076 48435134
RESTBL   DS    A                                                WC10076 48435234
LRESTBL  EQU   65                                               WC10076 48435334
DSNTRA   DC    A(0)               DSN TRANSLATION TABL START   WC10076  48435434
DSNTRE   DC    A(0)               DSN TRANSLATION TABL END     WC10076  48435534
DSNREGS  DS    4F                                               WC10076 48435634
*-----                                                                  48435734
WORK     DS    D          WORK FIELD                             WC0001 48435834
EXP2CNT  DS    D          NUMBER OF EXP2 EXPRESSIONS IN COMP=           48435934
SRCHCNT  DS    D          NUMBER OF SRCH EXPRESSIONS IN NAME=(          48436034
DELCNT   DS    D           COUNT OF SYSIN PDS LINES DELETED      WC0225 48436134
AMCTADDR DS    A          MCT ADDR FOR USING                    WC0367  48436234
MCTADDR  DS    A          MCT ADDR FOR IOAMEM                   WC0467  48436334
SAVER1   DS    A                                                        48436434
*SAVER1_2 DS    A          SAVE R1 IN ADDINCLB         BC10091 BC10093  48436534
SAVER2   DS    A                                                WC0237  48436634
SAVER3   DS    A                                                BC10268 48436734
SAVER9   DS    A                                                        48436834
SAVER9X  DS    A        ADDITIONAL SAVE OF R9 BAL REGISTER              48436934
SAVER10  DS    A                                               BC10093  48437034
SAVER14  DS    A                                                        48437134
SAVER15  DS    A                                                        48437234
SAVER15X DS    A                                                        48437334
CHKAMPPR DS    0A            CHKAMP PARAMETER                   BC10273 48437434
CHKAMP12 DS    A             CHKAMP PARAMETER R12               BC10273 48437534
CHKAMP11 DS    A             CHKAMP PARAMETER R11               BC10273 48437634
CHKAMPPA DS    A             CHKAMP PARAMETER ADDRESS INSIDE    BC10273 48437734
AFTBEGIN DS    A                   ADDRESS AFTER BEGIN                  48437834
CURRADDR DS    A                   ADDRESS OF LAST PARAM ON LINE        48437973
MOREADDR DS    A                   ADDR TO LOOK FOR ADDITIONAL PARAMS   48438034
ALINE#   DS    A                                                        48438134
AWORK    DS    A                                                        48438234
ACTMMEM  DS    A                   ADDR OF CTMMEM -> IOAMEM      WC0225 48438334
ERROR    DS    A      DCB ADDR OF ERROR FILE PASSED FROM OP014   WC0467 48438434
VARNMTBL DS    A      ADDR OF VAR-NAME TBL FROM OP018           BC10084 48438534
VARTABBF DS    A      ADDR OF VAR-TABL NAMES FROM OP018        BC10276  48438634
VARTABEN DS    A      ADDR OF VAR-TABL NAMES - END             BC10276  48438734
*VARTABON DS    CL24  AREA FOR TABL ORIGINAL NAME (MAY HAVE &) BC10276  48438834
VARTABON DS    CL(MAXTBLNM) TBL ORIG NAM AREA(MAY HAVE &)BC10276BC10351 48438934
CAS51PRC DS    A                    CTMCDPRC ADDRESS            BC10064 48439034
CTM5MEMN DS    A  51PRC PARM LIST:   MEMBR NAME POINTER PARM   BC10064  48439134
CTM5MEMP DS    A             MEMBR MEMORY POINTER PARM         BC10064  48439234
CTM5MEML DS    A             MEMBR LINE COUNT POINTER PARM     BC10064  48439334
CTM5WRKP DS    A             WORK AREA POINTER PARM             BC10064 48439434
CTM5ERRF DS    A         DCB ERROR FILE POINTER PARM            BC10064 48439534
CTM5ACTM DS    A             IOAMEM ADDRESS                     BC10064 48439634
CTM5RC   DC    A(RC)         RC ADDRESS                         BC10064 48439734
CTM5MCT  DS    A             MCT ADDR         BC0528            BC10064 48439834
         DC    A(DUMMY)      BEGIN NN FOR NSTNN NAME - NOT USED BC10064 48439934
         DC    A(PRODUCT)     'OPC'                         BC10370     48440034
         DC    A(L2VARS)      'NNNNNNNNNN'                  BC10370     48440134
CTM5VART DS    A       VARIABLE TABL LIST ADDR FROM 51PRC      BC10064  48440234
*                                                                       48440334
RC       DC    H'0'                                             BC10064 48440434
ASYSIN   DC    A(0)                ADDR OF SYSIN MEMBR   WC0031 WC0225  48440534
SYSINPRC DS    2F                  SAVE R11,R12                  WC0225 48440634
ENDSTEPA DS    A             ADDR OF END OF STEPNAME            WC0237  48440734
CHGSTART DC    A(0)          INIT TO 0                          WC0096  48440834
CHGEND   DS    A                                                WC0096  48440934
CALSTART DC    A(0)          CAL TABL                          BC10327  48441034
CALEND   DS    A             CAL TABL END                      BC10327  48441134
JOBSTART DS    F           XRF      START ADDRESS (MEMORY)      WC10012 48441234
JOBEND   DS    F           XRF      END ADDRESS (MEMORY)        WC10012 48441334
*WC10076 LOADJOB# DC    F'&JOBMAX' NUMBER OF APPLS IN THIS SITE WC10012 48441434
SVSETPOS DS    A        POS ON THE SET STMT FOR SETFORM DIRECTIVWC10026 48441534
WORKAPPL DS    CL16          WORK FIELD FOR ADDAPPL (RECOVER)   WC0237  48441634
RESOURCE DS    CL44                                                     48441734
NEWRES   DS    CL20                                                     48441834
MEMSYM   DS    CL12 MEMBR NAME FOR MEMSYM (L=12 FOR VARIABLES) BC0101   48441934
OPCMEMB  DS    CL20                MEMBR NAME FOR INCMEM                48442034
MEMBER   DS    CL8                 MEMBR NAME                           48442134
SAVSTPNM DS    CL8                 STEPNAME                    WC0001   48442234
RECVKEYW DS    CL8                 RECOVER KEYWORD PARAMETER   WC0001   48442334
CALENDAR DS    CL8                 DEFAULT CALENDAR NAME        BC10327 48442434
MEMADDR  DS    A                   MEMBR ADDRESS                        48442534
OPSTPARM DS    A                   OPSTAT PARM ADDRESS         WC10083  48442634
PROCADDR DS    A                                                        48442734
LINE#    DS    F                                                        48442834
LINELEN  DS    H            JCL LINELEN=70, DATA LINELEN=78     BC0283  48442934
AVAIL    DS    C          AVAIL CODED - NEED ADD/DEL COND   BC10433     48443034
QUANT    DC    CL6' '     QNT IS OF THE FORMAT [+|-]NNN       BC10192   48443134
OPNUM    DC    CL3' '              OPSTAT OPNUM PARAMETER        WC0096 48443234
WSNAM    DC    CL4' '              OPSTAT WSNAM PARAMETER        WC0096 48443334
JOBNAM   DC    CL8' '              OPSTAT JOBNAM PARAMETR        WC0096 48443434
APPLWORK DC    CL16' '             OPSTAT APPLID PARAMETR        WC0096 48443534
*APPLNEW  DC    CL8' '         OPSTAT APPL-NEW-NAME      WC0096 WC10012 48443634
STATUS   DC    CL1'C'              OPSTAT STATUS - DFLT 'C'     BC10360 48443734
*CTMCND   DC    C'&CTMCND'          CTMCND PROC NAME           WC10012  48443834
N        DC    C'0000000' INDEX FOR SET STMT (MULTI VAR ON LINE)BC10091 48443934
VARNDX   DC    C'0'       VAR NDX FOR SQZ REPLACEMENT VARNAME  BC10450  48444034
FLAGS    DC    X'00'               FLAGS BYTE                           48444134
CHANGES  EQU   X'01'               INDICATE CHANGES DONE                48444234
ACTION   EQU   X'02'      FLAG OFF(0)=INCLUDE, ON (1)=EXCLUDE           48444334
ININPUT  EQU   X'04'               INDICATE STARTING PROCESS INPUT      48444434
EXPCONT  EQU   X'08'      EXPECT A CONTINUATION OF COMP= CARD           48444534
FOUND    EQU   X'10'      SOMETHING FOUND ON //*%OPC CARD               48444634
SRCHCONF EQU   X'20'      EXPECT A CONTINUATION OF SEARCH CARD          48444734
FETCHCON EQU   X'40'      EXPECT A CONTINUATION OF FETCH WITH COMP=     48444834
MORE     EQU   X'80'      MULTIPLE COMP= VARS ON LINE                   48444934
FLAGS2   DC    X'00'                                                    48445034
FIRSTINC EQU   X'01'      FIRST INCLIB INSERTED                         48445134
NOTEMP   EQU   X'02'      NOT A &&-TEMP                                 48445234
DELSTEPF EQU   X'04'      THE RECOVER FUNCTION USES DELSTEP      WC0001 48445334
DELWAIT  EQU   X'08'      A DELSTEP ENDIF IS WAITING             WC0001 48445434
DELRNGFL EQU   X'10'      IN MIDDLE OF DELSTEP RANGE             WC0001 48445534
OPENPAR  EQU   X'20'      FLAG TO INDICATE OPEN-PAR CODED        WC0001 48445634
$RELSUCC EQU   X'40'      RELSUCC BEING PROCESSED                WC0467 48445734
NOADV    EQU   X'80'   DONT ADVANCE PARAMETER POINTER IN R7 TBL WC0001  48445834
*                                                                       48445934
FLAGS0   DC    X'00'                                             WC0001 48446034
$CONCAT  EQU   X'80'      &A.CONST VAR + CONST CONCAT          BC10035  48446134
SCAN     EQU   X'40'      SCAN DIRECTIVE ENCOUNTERED             WC0082 48446234
PGM      EQU   X'20'      PGM= IN OPCBATCH                       WC0225 48446334
SYSINPDS EQU   X'10'      SYSIN IS A PDS                        WC0225  48446434
MULTSYSN EQU   X'08'                                            WC0225  48446534
SEQFLAG  EQU   X'04'                                            WC0225  48446634
SEQEMPTY EQU   X'02'                                            WC0225  48446734
ADDPWAIT EQU   X'01'      WAITING TO ADD INCLIB FOR ADDPROC     WC0237  48446834
*                                                                       48446934
FLAGS1   DC    X'00'                                          WC10026   48447034
$TIME    EQU   X'01'      SETFORM TIME                        WC10026   48447134
$CONST   EQU   X'02'      IN MIDST OF CONSTANT PROCESSING     WC10026   48447234
$VARPRC  EQU   X'04'      HAS A SETFORM VAR BEEN ENCOUNTERD YET?BC10064 48447334
$$VAR    EQU   X'08'      USE $YEAR INSTEAD OF OYEAR            BC10075 48447434
$VARXST  EQU   X'10'      A VARIABLE EXISTS IN JCL LINE       BC10084   48447534
$SRSCONT EQU   X'40'      SRSTAT COMMAND HAS CONTINUATION       WC10273 48447634
$FNLSQZ  EQU   X'80'      FINAL EMBEDDED BLNK SQZ DONE         BC10370  48447734
*                                                                       48447834
FLAGR    DC    X'00'      FLAGS FOR CONTINUATION OF RECOV PARAM WC0244  48447934
$ADDAP   EQU   X'01'                                            WC0244  48448034
$ADDPR   EQU   X'02'                                            WC0244  48448134
$DELST   EQU   X'04'                                            WC0244  48448234
$JOBCO   EQU   X'08'                                            WC0244  48448334
*$STEPC   EQU   X'10'                                            WC0244 48448434
$ERRST   EQU   X'20'                                            WC0244  48448534
*$RELSU   EQU   X'40'                                            WC0244 48448634
RECVMORE EQU   X'80'     CONTINUATION ON RECOVER STMT           WC0244  48448734
FLAGDSN  DC    X'00'                                            WC10076 48448834
$NEW_NAME_EXPECTED EQU X'80'                                    WC10076 48448934
FLAGSCAN DC    X'00'                                            BC10268 48449034
$RESOFF  EQU   X'01'                                            BC10268 48449134
$SFVPER  EQU   X'02'       LAST TOKEN ADDED TO SET LINE WAS %%. BC10268 48449234
$SFVDBDT EQU   X'04'       LAST TOKEN IS DOUBLE DOT             BC10312 48449334
*                                                                       48449434
VARLINE  DS    CL80                                             BC10276 48449534
LINE     DS    CL80                                                     48449634
         DS    CL80                                                     48449734
VAR      DC    CL30' '                                                  48449834
OPER     DC    CL2' '                                                   48449934
GOTOCNT1 DC    PL2'0'     NUMBER OF BEGIN DIRECTIVES                    48450034
GOTOCNT2 DC    PL2'0'     NUMBER OF COMP= CONTINUATION LINES            48450134
IFCNT1   DC    CL2'00'                                                  48450234
IFCNT2   DC    CL2'00'                                                  48450334
CHGFILEN EQU   32          LENGTH OF CHGFILE ENTRY FOR GETMAIN BC10360  48450434
MAXTBLNM EQU   50      MAX LENGTH OF TWS SEARCH/TABL NAME     BC10351   48450534
MYLIBSYM DC    C'//* %%SET %%MYLIBSYM=' SET TO REQ LIBSYM       BC10276 48450634
MYLIBNAM DS    CL44              THIS MUST FOLLOW MYLIBSYM      BC10276 48450734
MYMEMSYM DC    C'//* %%SET %%MYMEMSYM='    SET TO REQ MEMSYM    BC10276 48450834
*MYMEMNAM DC    CL(L'VTCTMNM)' '  MUST FOLLOW MYMEMSYM BC10276 BC10351  48450934
MYMEMNAM DC    CL(L'TABLE)' '     MUST FOLLOW MYMEMSYM         BC10351  48451034
*  THE MYMEMNAM MAY BE > 8 CHARS (WHICH IS INVALID)                     48451134
*  AND THIS MAY OCCUR (>8) IN 2 WAYS                                    48451234
* 1. THE SEARCH OR TABLE NAME MAY NOT EXIST ON THE VATTAB XLATE FILE    48451334
* 2. THE SEARCH OR TABLE NAME MAY CONTAIN SYMBOLIC VARIABLES WHICH ARE  48451434
*    NOT RESOLVED UNTIL RUN-TIME                                        48451534
*  IN EITHER CASE THE NAME CANT BE FOUND ON THE VARTAB XLATE FILE, SO   48451634
*    WE ADD A SET STMT TO DO A SUBSTRING ON (RESOLVED) %%MYMEMSYM TO    48451734
*    CUT IT TO 8 CHAR AND ISSUE A WARNING:                              48451834
*  MSGID: MEMSYM MEMBR NAME MAY NOT EXIST OR MAY BE INCORRECTLY         48451934
*         RESOLVED AT RUN TIME                                          48452034
*    EXPLANATION: THE SEART/TABLE NAME MAY NOT EXIST IN THE JCLVAR      48452134
*                 FILE OR THE NAME CONTAINS SYMBOLIC VARIABLES          48452234
*                 WHICH ARE ONLY RESOLVED AT RUN TIME AND MAY           48452334
*                 RESULT IN MEMSYM NAME WHICH EXCEEDS 8 CHARS.          48452434
*    USER ACTION: ENSURE THAT THE MEMSYM NAME POINTS TO AN EXISTING     48452534
*                 MEMBR IN THE LIBSYM LIBRARY (CREATED FROM THE TWS     48452634
*                 JCLVAR FILE)                                          48452734
SUBSTR   DC   C'//* %%SET %%MYMEMSYM = %%SUBSTR %%MYMEMSYM 1 8' BC10351 48452834
*LIBSYM   DC    C'//* %%LIBSYM %%MYLIBSYM %%MEMSYM %%MYMEMSYM'  BC10276 48452934
LIBSYM   DC    C'//* %%INCLIB %%MYLIBSYM %%INCMEM %%MYMEMSYM' BC10693   48453034
*BC10276 LIBSYM   DC    C'//* %%LIBSYM '                       WC0083   48453134
*BC10276 LIBNAM   DS    CL44      THIS MUST FOLLOW LIBSYM       WC0083  48453234
*BC10276 LIBMEM   DC    C' %%MEMSYM '                           WC0083  48453334
*GTABLE  DC    C'    %%GLOBAL '                        BC0102   WC10076 48453434
GTABLE@  DC    C'    %%GLOBAL '                                 WC10076 48453534
IF       DC    C'//* %%IF '                                             48453634
ELSE     DC    C'//*   %%ELSE'                                          48453734
GOTO     DC    C'//*   %%GOTO LABEL'                                    48453834
LABEL    DC    C'//* %%LABEL LABEL'                                     48453934
ENDIF    DC    C'//* %%ENDIF'                                           48454034
SETSTMT  DC    C'//* %%SET %%'       FOR SETFORM DIRECTIVE      WC10026 48454134
RESOFF   DC    C'//*   %%RESOLVE OFF'                           BC10268 48454234
RESON    DC    C'//*   %%RESOLVE YES'                           BC10268 48454334
AEVAR    DS    CL6     A-E VAR (MONTH, DAY, JULDAY, HH, MINUTE) WC10026 48454434
OFLAG    DC    CL1' '  ' '=STNDRD DAT; 'O'=ORIG SCHEDDAT; $=YYYYWC10026 48454534
DSN      DS    CL44     DSN OF PDS ON BATCH TERMINAL SYSIN       WC0225 48454634
*DDNAME   DC    CL8'SYSINLIB'  DDNAME FOR DYN ALLOC OF SYSIN LIB WC0225 48454734
SYSINMEM DS    CL8      PDS MEMBR NAME ON BATCH TERM SYSIN      WC0225  48454834
USERID   DC    CL8' '                                            WC0225 48454934
SFVDVAR  DC    CL8' '    OPC DYNAMIC VAR NAME EXTRACTED         BC10268 48455034
SFVUVAR  DC    CL8' '    OPC VAR NAME TO BE SET BY OPC SETVAR   BC10268 48455134
SFVUDVN  DC    CL8' '    OPC DYNAMIC VAR USED IN SETVAR CYY,... BC10268 48455234
SFVSIGN  DC    CL1' '    SIGN SPECIFIED IN SETVAR               BC10268 48455334
SFVNUM   DC    CL3' '    NUM SPECIFIED IN SETVAR                BC10268 48455434
SFVNUM2  DC    CL3' '    SETVAR SUBSTR LENGTH PARAM             BC10370 48455534
SFVFUNC  DC    CL8' '    FUNC SPECIFIED IN SETVAR               BC10268 48455634
SFVUNIT  DC    CL1' '    UNIT SPECIFIED IN SETVAR (Y/M/W/ )     BC10268 48455734
FROMLINE DC    F'0'                                              WC0225 48455834
GETCNT   DC    F'100'                                            WC0225 48455934
REP      DC    CL1'R'        REPLACE                             WC0225 48456034
*DDMM     DC    CL16' %%ODAY.%%OMONTH'                BC0118   WC10012  48456134
DELADD   DC    C'DELETE COND '                                          48456247
SFVDEF1  DC    C'//*%OPC SETVAR '                               BC10276 48456348
SFVDEF2  DC    C'=('                                            BC10276 48456448
SFVDEF3  DC    C'+0CD)'                                         BC10276 48456548
MAXAPPL  DC    PL2'5'           MAX ADDAPPLS OR RELSUCCS ALLOWEDBC10758 48456648
                                                                        48456734
ERROR003 DC    CL133' '                                        BC10893  48456834
         ORG   ERROR003                                        BC10893  48456934
         DC    CL16'-CTMOP015-06E - '                          BC10893  48457034
ERR03MEM DS    CL8                                             BC10893  48457134
         DC    CL1' '                                          BC10893  48457234
ERR03DES DS    CL108                                           BC10893  48457334
                                                                        48457434
SEQFILE  DCB   DDNAME=SEQFILE,DSORG=PS,MACRF=(GL,PM),           WC0225 *48457534
               EODAD=SEQEOF,EXLST=JFCBXLST,                     WC0225 *48457634
               DCBE=SEQDCBE                                    WC10075  48457734
SYSINLIB DCB   DDNAME=SYSINLIB,DSORG=PS,MACRF=(GL,PM),RECFM=FB, WC0225 *48457834
               LRECL=80,BLKSIZE=3120,EODAD=SYSINEOF,EXLST=JFCBXLS2,    *48457934
               DCBE=SYSDCBE                                    WC10075  48458034
         LTORG                                                          48458199
*BC10268 TRITSELF DC    0XL256'00',256AL1(*-TRITSELF) BASE FOR  WC10083 48458434
SAVLENV  DS    F        LENG OF VAR NAME IN JCL/DATA LINE       BC10450 48458534
EXP2LEN  DC    A(L'EXP2*100)                                            48458634
SAVDELIM DS    CL1                                               WC0001 48458734
SAVLENG  DS    H                                                 WC0001 48458834
RECVCNT  DS    PL2                                               WC0001 48458934
DELSTPTR DC   2CL8' '  TABL OF DELSTEP RANGE NAMES              WC0001  48459034
*SAVCOL   DS    H     COLUMN# FROM ?NNVAR                      WC10049  48459134
*SAVVALLN DS    X     LENGTH OF SYSTEM VARIABLE'S VALUE        WC10049  48459234
*SAVPOS   DS    A          ADDRESS  OF ?NNVAR IN LINE          WC10049  48459334
IDSTAMP  DC    C'** OPC TO CTM JCL CONV, V9.X'                BC10433   48459434
         COPY  CTMOPROR   COPY IN FILE LAYOUT                    WC0237 48459534
         IOAMMEM DSECT=NO                                        WC0467 48459634
PARCOMA  DC    256X'00'      CLOSE-PAREN, COMA, BLNK                    48459734
         ORG   PARCOMA+C')'  END OF PARAMETER                           48459834
         DC    C')'                                                     48459934
         ORG   PARCOMA+C','                                             48460034
         DC    C','                                                     48460134
         ORG   PARCOMA+C' '                                             48460234
         DC    C' '                                                     48460334
         ORG                                                            48460434
*---------- ALL FIELDS BELOW MUST BE ADDRESSABLE VIA ADCONS ------      48460534
INCLIB   DC    C'    %%INCLIB DDNAME=EQQJBLIB %%INCMEM '       BC10370  48460634
INCLIB2  DC    C'//* %%INCLIB DDNAME=EQQPRLIB %%INCMEM '       BC10370  48460734
DUMMY    DC    PL3'0'        UNUSED    51PRC     BC10064 BC10370        48460834
PRODUCT  DC    CL8'OPC'                51PRC             BC10370        48460934
L2VARS   DC    C'NNNNNNNNNN'           51PRC             BC10370        48461034
SEQDCBE  DCBE  RMODE31=BUFF                                    WC10075  48461134
SYSDCBE  DCBE  RMODE31=BUFF                                    WC10075  48461234
NONBLANK DC    X'FF',255AL1(*-NONBLANK)   INTRMK                        48461334
         ORG   NONBLANK+C' '                                            48461434
         DC    X'00'                                                    48461534
         ORG                                                            48461634
TRTRANS  DC    XL256'00'       DYNAMIC BUILD TABL               WC10083 48461734
GLOBAL   DC    256X'00'                                         BC10327 48461834
         ORG   GLOBAL+C'%'  END OF PARAMETER                    BC10327 48461934
         DC    X'FF'                                            BC10327 48462034
         ORG   GLOBAL+C'*'                                      BC10327 48462134
         DC    X'FF'                                            BC10327 48462234
         ORG   ,                                                BC10327 48462334
TRITSELF DC    0XL256'00',256AL1(*-TRITSELF) USE AS A BASE FOR  BC10268 48462434
*  SET DEFAULTS FOR ( ) | AND COMMA TO XLATE TO { } ! ;                 48462534
         ORG   TRITSELF+C'('       ()| ARE BOOLEAN OPERATORS BC10360    48462634
         DC    C'{'                                          BC10360    48462734
         ORG   TRITSELF+C')'                                 BC10360    48462834
         DC    C'}'                                          BC10360    48462934
         ORG   TRITSELF+C'|'                                 BC10360    48463034
         DC    C'!'                                          BC10360    48463134
         ORG   TRITSELF+C','       BLT DELIM: COND-NAME,ODAT BC10360    48463234
         DC    C';'                                          BC10360    48463334
         ORG   TRITSELF+C'*'                                 BC10371    48463434
         DC    C'X'                                          BC10371    48463534
         ORG   ,                                             BC10360    48463634
NOERREC  DS    CL80          NOERROR RECORD                      WC0001 48463734
*BC10276 TABLE DC8CL12' 'TBL NAMES FOR SEARCH DIRECTV(L=12)BC0101WC0237 48463834
*TABLE    DC   8CL(L'VTCTMNM)' ' TBL NAMES FOR SEARCH DIRECTV  BC10276  48463934
TABLE    DC   8CL(MAXTBLNM)' ' TBL NAMES FROM SEARCH DIRECTV  BC10351   48464034
DELSTPTB DC  10CL8' '  TABL OF ALL DELSTEP NAMES         WC0001 WC0237  48464134
PROCNMTB DC  10CL8' '  TABL OF ALL ADDPROC NAMES                WC0237  48464234
         DS    0F         LIST OF RECOVER PARAMS                 WC0001 48464334
RECVTAB  DC    C'ERRSTEP ',A(RTNERRST)                           WC0001 48464434
RECVTABL EQU   *-RECVTAB      LENGTH OF ENTRY                    WC0001 48464534
         DC    C'JOBCODE ',A(RTNJOBCO)                           WC0001 48464634
         DC    C'STEPCODE',A(RTNSTEPC)                           WC0001 48464734
         DC    C'TIME    ',A(RTNTIME)                            WC0001 48464834
         DC    C'DELSTEP ',A(RTNDELST)                           WC0001 48464934
         DC    C'ADDPROC ',A(RTNADDPR)                           WC0237 48465034
         DC    C'RESSTEP ',A(RTNRESST)                           WC0001 48465134
         DC    C'CALLEXIT',A(RTNERROR)    NOT SUPPORTED          WC0001 48465234
         DC    C'RESTART ',A(RTNRESTA)                           WC0001 48465334
         DC    C'RESJOB  ',A(RTNERROR)    NOT SUPPORTED          WC0001 48465434
         DC    C'ADDAPPL ',A(RTNADDAP)                           WC0001 48465534
         DC    C'RELSUCC ',A(RTNRELSU)     YES                   WC0237 48465634
         DC    C'RELSUC  ',A(RTNRELSU)     YES                  BC10354 48465734
         DC    C'ALTWS   ',A(RTNERROR)    NOT SUPPORTED          WC0001 48465834
*BC10433 DC    C'ALTJOB  ',A(RTNERROR)    NOT SUPPORTED          WC0001 48465934
         DC    C'ALTJOB  ',A(RTNALTJO)    --> RERUNMEM          BC10433 48466034
         DC    X'FF'                                             WC0001 48466134
CODESTBL DS    0CL10               LENG OF TBL ENTRY            BC10370 48466234
         DC    C'CLN  ',C'*UKNW'              TWS CLEANUP ERRORSBC10370 48466334
         DC    C'JCCE ',C'*UKNW'              ERR DUR JCC PRC   BC10370 48466434
         DC    C'CAN  ',C'JNSUB'              OPER CANC BEF EXECBC10370 48466534
         DC    C'OJCV ',C'JNSUB'              ERR DUR JCL VARSUBBC10370 48466634
         DC    C'OSUF ',C'JFAIL'              FAIL TO RETR JCL  BC10370 48466734
         DC    C'CCUN ',C'*UKNW'              OPC CODE          BC10370 48466834
         DC    C'FLSH ',C'FLUSH'                                BC10370 48466934
         DC    C'JCL  ',C'JFAIL'              JCL ERR AFTR STRT BC10370 48467034
         DC    C'JCLI ',C'JNRUN'              JCL ERR BEFR STRT BC10370 48467134
         DC    C'OSUB ',C'JNSUB'              FAILURE SUBMITING BC10370 48467234
         DC    C'PCAN ',C'JLOST'              PRINT OPER CANCEL BC10370 48467334
         DC    X'FF'                                            BC10370 48467434
ERROR006 DC    CL133' '                                         BC10893 48467560
         ORG   ERROR006                                         BC10893 48467660
         DC    CL16'-CTMOP015-08W - '                           BC10893 48467760
ERR06MEM DS    CL8                                              BC10893 48467860
         DC    CL36' SET STMT VARIABLE NAME UNRESOLVED: '       BC10893 48467960
ERR06VAR DS    CL30                                             BC10893 48468060
         DC    CL43' '                                          BC10893 48468160
DSNMAX   EQU   4000                                                     48468260
DEFBLOCK DS    A                                                WC10076 48468360
MFCALL   DS    6F                                               WC10076 48468460
         DS    0F                                                WC0083 48468534
LIBXLST  DC    X'87',AL3(LIBSYMDS)                               WC0083 48468634
LIBSYMDS DS    CL176                    JFCB AREA                WC0083 48468734
LIBSYMDD DCB   DSORG=PO,DDNAME=LIBSYM,MACRF=(W),EXLST=LIBXLST,   WC0083*48468834
               DCBE=LIBDCBE                                 WC10075     48468934
CASECODE DCB   DSORG=PS,DDNAME=CASECODE,MACRF=GL,EODAD=NOCASES, WC0001 *48469034
               DCBE=CASDCBE                                 WC10075     48469134
NOERROR  DCB   DSORG=PS,DDNAME=NOERROR,MACRF=GM,EODAD=NOERRFIL, WC0001 *48469234
               DCBE=NERRDCBE                                 WC10075    48469334
RECVEXT  DCB   DSORG=PS,DDNAME=RECVEXT,MACRF=PM,RECFM=FB,       WC0001 *48469434
               DCBE=RECVDCBE                                 WC10075    48469534
CHGFILE  DCB   DSORG=PS,DDNAME=DACHANGE,MACRF=GL,EODAD=EOFCHG,  WC0096 *48469634
               DCBE=CHGDCBE                                 WC10075     48469734
XRFFILE  DCB   DDNAME=DAXRF,DSORG=PS,MACRF=GM,EODAD=EOFJOB,     WC10012*48469834
               DCBE=XRFDCBE                                 WC10075     48469934
RESNAME  DCB   DSORG=PS,DDNAME=RESNAME,MACRF=GL,EODAD=EOFRES,   WC0221 *48470034
               DCBE=RESDCBE                                 WC10075     48470134
DABATCH  DCB   DSORG=PS,DDNAME=DABATCH,MACRF=GL,EODAD=EOFBAT,   WC0225 *48470234
               DCBE=BATDCBE                                 WC10075     48470334
LIBDCBE  DCBE  RMODE31=BUFF                                 WC10075     48470434
CASDCBE  DCBE  RMODE31=BUFF                                 WC10075     48470534
NERRDCBE DCBE  RMODE31=BUFF                                 WC10075     48470634
RECVDCBE DCBE  RMODE31=BUFF                                 WC10075     48470734
CHGDCBE  DCBE  RMODE31=BUFF                                 WC10075     48470834
XRFDCBE  DCBE  RMODE31=BUFF                                 WC10075     48470934
RESDCBE  DCBE  RMODE31=BUFF                                 WC10075     48471034
BATDCBE  DCBE  RMODE31=BUFF                                 WC10075     48471134
EXP2     DC    100CL30' '       COMP EXPRESSIONS                        48471234
CASETBL  DC    (20*11)CL5' '  MAX: 20 CASES, 10 CODES PER CASE   WC0001 48471334
HEXTRANS DC    256X'00'  TRANSLATE HEX TO CHAR                   WC0001 48471434
         ORG   HEXTRANS+C'A'                                     WC0001 48471534
         DC    X'AABBCCDDEEFF'                                   WC0001 48471634
         ORG   HEXTRANS+C'0'                                     WC0001 48471734
         DC    X'00112233445566778899'                           WC0001 48471834
         ORG                                                   , WC0001 48471934
AMPERSND DC    256X'00'        FIND BEGINNING OF VARIABLE (&, %, ?)     48472034
         ORG   AMPERSND+C'&&'                                           48472134
         DC    C'&&'                                            WC10049 48472234
         ORG   AMPERSND+C'%'                                            48472334
         DC    C'%'                                             WC10049 48472434
         ORG   AMPERSND+C'?'                                    WC10049 48472534
         DC    C'?'                                             WC10049 48472634
         ORG                                                            48472734
BLANK    DC    256X'00'             FIND FIRST BLANK                    48472834
         ORG   BLANK+C' '                                               48472934
         DC    C' '                      INTRMK                         48473034
         ORG                                                            48473134
TRTPER   DC    256X'00'                                         WC10012 48473234
         ORG   TRTPER+C'.'                                      WC10012 48473334
         DC    C'.'                                              WC0237 48473434
         ORG                                                            48473534
EQUAL    DC    256X'00'  FIND END OF KEYWORD                     WC0001 48473634
         ORG   EQUAL+C'='                                        WC0001 48473734
         DC    C'-'                                              WC0001 48473834
         ORG                                                   , WC0001 48473934
PLMIN    DC    256X'00'  FIND SETVAR ASSIGNMENT ACTION + / -    BC10268 48474034
         ORG   PLMIN+C'-'                                       BC10268 48474134
         DC    C'-'                                             BC10268 48474234
         ORG   PLMIN+C'+'                                       BC10268 48474334
         DC    C'+'                                             BC10268 48474434
         ORG   PLMIN+C')'                                       BC10370 48474534
         DC    C'+'         TO SIMULATE +0CD WHEN ')' ENCOUNTERDBC10370 48474634
         ORG                                                  , BC10268 48474734
DELIM    DC    256X'00'          VARIABLE DELIMITER CHARACTER           48474834
         ORG   DELIM+C''''                                              48474934
         DC    C''''                                                    48475034
         ORG   DELIM+C'&&'                                              48475134
         DC    C'&&'                                                    48475234
         ORG   DELIM+C'('                                               48475334
         DC    C'('                                                     48475434
         ORG   DELIM+C')'                                               48475534
         DC    C')'                                                     48475634
         ORG   DELIM+C','                                               48475734
         DC    C','                                                     48475834
         ORG   DELIM+C'/'                                               48475934
         DC    C'/'                                                     48476034
         ORG   DELIM+C'*'                                               48476134
         DC    C'*'                                                     48476234
         ORG   DELIM+C'%'                                               48476334
         DC    C'%'                                                     48476434
         ORG   DELIM+C'-'                                               48476534
         DC    C'-'                                                     48476634
         ORG   DELIM+C'+'                                               48476734
         DC    C'+'                                                     48476834
         ORG   DELIM+C'='                                               48476934
         DC    C'='                                                     48477034
         ORG   DELIM+C'?'                                               48477134
         DC    C'?'                                                     48477234
         ORG   DELIM+C' '                                               48477334
         DC    C' '                                                     48477434
         ORG   DELIM+C'.'                                   BC0325      48477534
         DC    C'.'                                         BC0325      48477634
         ORG                                                            48477734
NUMTRT   DC    256X'FF'  VALIDATE NUMERICS                       WC0001 48477834
         ORG   NUMTRT+C'0'                                     WC0001   48477934
         DC    10X'00'                                           WC0001 48478034
         ORG                                                   , WC0001 48478134
PAREN    DC    256X'00'                                         WC0096  48478234
         ORG   PAREN+C'('                                       WC0096  48478334
         DC    C'('                                             WC0096  48478434
         ORG   PAREN+C')'                                       WC0096  48478534
         DC    C')'                                             WC0096  48478634
         ORG   ,                                                WC0096  48478734
OPNPAREN DC    256X'00'                                                 48478834
         ORG   OPNPAREN+C'('                                            48478934
         DC    C'('                        INTRMK                       48479034
         ORG                                                            48479134
PERCENT  DC    256AL1(*-PERCENT)  XLATE % TO * IN NOERROR CODES  WC0001 48479234
         ORG   PERCENT+C'%'                                      WC0001 48479334
         DC    C'*'                                              WC0001 48479434
         ORG                                                   , WC0001 48479534
SEPTAB   DC    256X'01'                                                 48479634
         ORG   SEPTAB+C'$'    NOT A SEPERATOR                   BC10268 48479734
         DC     X'00'                                           BC10268 48479834
         ORG   SEPTAB+C'@'                                      BC10268 48479934
         DC    X'00'                                            BC10268 48480034
         ORG   SEPTAB+C'#'    NOT A SEPERATOR                   BC10268 48480134
         DC    X'00'                                            BC10268 48480234
         ORG   SEPTAB+C'A'    A THRU I NOT A SEPARATOR          BC10268 48480334
         DC    9X'00'                                           BC10268 48480434
         ORG   SEPTAB+C'J'    J THRU R NOT A SEPARATOR          BC10268 48480534
         DC    9X'00'                                           BC10268 48480634
         ORG   SEPTAB+C'S'    S THRU Z NOT A SEPARATOR          BC10268 48480734
         DC    8X'00'                                           BC10268 48480834
         ORG   SEPTAB+C'0'    0 THRU 9 NOT A SEPERATOR          BC10268 48480934
         DC    10X'00'                                          BC10268 48481034
         ORG   SEPTAB+C'_'    NOT A SEPERATOR                   BC10268 48481134
         DC    X'00'                                            BC10268 48481234
         ORG   SEPTAB+C'&&'    NOT A SEPERATOR                  BC10268 48481334
         DC    X'00'                                            BC10268 48481434
         ORG   SEPTAB+C'A'    NOT A SEPERATOR                   BC10268 48481534
         DC     X'00'                                           BC10268 48481634
         ORG   SEPTAB+X'41'   X'41' THRU X'49' NOT A SEPARATOR  BC10268 48481734
         DC    9X'00'                                           BC10268 48481834
         ORG   SEPTAB+X'51'   X'51' THRU X'59' NOT A SEPARATOR  BC10268 48481934
         DC    9X'00'                                           BC10268 48482034
         ORG   SEPTAB+X'62'   X'62' THRU X'69' NOT A SEPARATOR  BC10268 48482134
         DC    8X'00'                                           BC10268 48482234
         ORG   SEPTAB+X'71'   X'71'            NOT A SEPARATOR  BC10268 48482334
         DC    X'00'                                            BC10268 48482434
         ORG   SEPTAB+X'81'   X'81' THRU X'89' NOT A SEPARATOR  BC10268 48482534
         DC    9X'00'                                           BC10268 48482634
         ORG   SEPTAB+X'91'   X'91' THRU X'99' NOT A SEPARATOR  BC10268 48482734
         DC    9X'00'                                           BC10268 48482834
         ORG   SEPTAB+X'A2'   X'A2' THRU X'A9' NOT A SEPARATOR  BC10268 48482934
         DC    8X'00'                                           BC10268 48483034
         ORG   ,                                                BC10268 48483134
*.NOTESA9 ANOP                                           WC0001 WC0237  48483234
JFCBXLST DS    0F                                               WC0225  48483334
         DC    X'87',AL3(JFCBAREA)    JFCB FOR SEQFILE          WC0225  48483434
JFCBAREA DS    CL176                                            WC0225  48483534
JFCBXLS2 DS    0F                                               WC0225  48483634
         DC    X'87',AL3(JFCBARE2)    JFCB FOR SYSINLIB         WC0225  48483734
JFCBARE2 DS    CL176                                            WC0225  48483834
COMMABLK DC    256X'00'                                                 48483934
         ORG   COMMABLK+C','                                            48484034
         DC    C','                               INTRMK                48484134
         ORG   COMMABLK+C' '                                            48484234
         DC    C' '                               INTRMK                48484334
         ORG                                                            48484434
QUOTAB   DC    256X'00'                                                 48484534
         ORG   QUOTAB+C''''                                             48484634
         DC    C''''                              INTRMK                48484734
         ORG                                                            48484834
TRTPAREN DC    256X'00'                                         WC0225  48484934
         ORG   TRTPAREN+C'('       FOR PDS MEMEBER              WC0225  48485034
         DC    C'('                                             WC0225  48485134
         ORG   TRTPAREN+C')'                                    WC0225  48485234
         DC    C')'                                             WC0225  48485334
         ORG   TRTPAREN+C','       FOR SEQUENTIAL FILE          WC0225  48485434
         DC    C'X'                                             WC0225  48485534
         ORG   TRTPAREN+C' '       FOR SEQUENTIAL FILE          WC0225  48485634
         DC    C'X'                                             WC0225  48485734
         ORG                                            ,       WC0225  48485834
EQFFTAB  DC    256X'00'         TO SEARCH VAR TABL LIST       BC10064   48485934
         ORG   EQFFTAB+X'FF'    VARNAME=VARVALUE DELIM         BC10064  48486034
         DC    X'FF'                                           BC10064  48486134
         ORG   ,                                               BC10064  48486234
*NUMTAB  DC    256X'FF'                                        WC10049  48486334
**       ORG   NUMTAB+C'0'                                     WC10049  48486434
**       DC    10X'00'                                         WC10049  48486534
**       ORG                                                 , WC10049  48486634
**VARTBL   DS    0CL14       LOOK-UP TBL FOR ?-VARIABLES        WC10049 48486734
* EACH ENTRY CONSISTS OF 4 PARTS, VARIABLE-NAME, VAR-NAME-LENG,         48486834
*                VALUE-LENG, ALTERNATE VAR-NAME    8+1+1+4              48486934
* SEE MEMBR 'SYSTEM' FOR COMPLETE LISTING OF VARIABLES AND A-E EQUIVAL  48487034
**       DC    CL8'OHH     ',X'03',X'02',CL4' '                 WC10049 48487134
**       DC    CL8'OHHMM   ',X'05',X'04',CL4' '                 WC10049 48487234
**       DC    CL8'MINUTE  ',X'06',X'02',CL4' '          MM     WC10049 48487334
**       DC    CL8'CHH     ',X'03',X'02',CL4' '                 WC10049 48487434
**       DC    CL8'CHHMM   ',X'05',X'04',CL4' '                 WC10049 48487534
**       DC    CL8'ODAY    ',X'04',X'01',CL4'ZZZZ'              WC10049 48487634
**       DC    CL8'CDAY    ',X'04',X'01',CL4' '  1 DIGIT WDAY   WC10049 48487734
**       DC    CL8'CDD     ',X'03',X'02',CL4' '                 WC10049 48487834
**       DC    CL8'CDDD    ',X'04',X'03',CL4' '                 WC10049 48487934
**       DC    CL8'CDDMMYY ',X'07',X'06',CL4' '                 WC10049 48488034
**       DC    CL8'CMM     ',X'03',X'02',CL4' '                 WC10049 48488134
**       DC    CL8'CMMYY   ',X'05',X'04',CL4' '                 WC10049 48488234
**       DC    CL8'CYMD    ',X'04',X'08',CL4' '  YYYYMMDD       WC10049 48488334
**       DC    CL8'CYY     ',X'03',X'02',CL4' '                 WC10049 48488434
**       DC    CL8'CYYDDD  ',X'06',X'05',CL4' '                 WC10049 48488534
**       DC    CL8'CYYMM   ',X'05',X'04',CL4' '                 WC10049 48488634
**       DC    CL8'CYYMMDD ',X'07',X'06',CL4' '                 WC10049 48488734
**       DC    CL8'CYYYY   ',X'05',X'04',CL4' '                 WC10049 48488834
**       DC    CL8'CYYYYMM ',X'07',X'06',CL4' '                 WC10049 48488934
**       DC    CL8'ODD     ',X'03',X'02',CL4' '                 WC10049 48489034
**       DC    CL8'ODDD    ',X'04',X'03',CL4' '                 WC10049 48489134
**       DC    CL8'ODMY1   ',X'05',X'06',CL4' '   DDMMYY        WC10049 48489234
**       DC    CL8'ODMY2   ',X'05',X'08',CL4' '   DD/MM/YY      WC10049 48489334
**       DC    CL8'OMM     ',X'03',X'02',CL4' '                 WC10049 48489434
**       DC    CL8'OMMYY   ',X'05',X'04',CL4' '                 WC10049 48489534
**       DC    CL8'OYM     ',X'03',X'06',CL4' '   YYYYMM        WC10049 48489634
**       DC    CL8'OYMD    ',X'04',X'08',CL4' '   YYYYMMDD      WC10049 48489734
**       DC    CL8'OYMD1   ',X'05',X'06',CL4' '   YYMMDD        WC10049 48489834
**       DC    CL8'OYMD2   ',X'05',X'08',CL4' '   YY/MM/DD      WC10049 48489934
**       DC    CL8'OYMD3   ',X'05',X'08',CL4' '   YYYYMMDD      WC10049 48490034
**       DC    CL8'OYY     ',X'03',X'02',CL4' '                 WC10049 48490134
**       DC    CL8'OYYDDD  ',X'06',X'05',CL4' '                 WC10049 48490234
**       DC    CL8'OYYMM   ',X'05',X'04',CL4' '                 WC10049 48490334
**       DC    CL8'OYYYY   ',X'05',X'04',CL4' '                 WC10049 48490434
**       DC    CL8'OADOWNER',X'08',X'08',CL4' '                 WC10049 48490534
**       DC    CL8'OADID   ',X'05',X'14',CL4' '  20 BYTE GROUP  WC10049 48490634
**       DC    CL8'OJOBNAME',X'08',X'08',CL4' '                 WC10049 48490734
**       DC    CL8'OWW     ',X'03',X'02',CL4' ' 2 BYTE WEEK NUMBWC10049 48490834
**       DC    CL8'OWWD    ',X'04',X'03',CL4' '  WEEK # + DAY NOWC10049 48490934
**       DC    CL8'CWW     ',X'03',X'02',CL4' '                 WC10049 48491034
**       DC    CL8'CWWD    ',X'04',X'03',CL4' '                 WC10049 48491134
**       DC    X'FF'                       END OF TBL           WC10049 48491234
BATTBL   DC    10CL9' '         OPC PGM/PROC NAME TBL           WC0225  48491334
*RESTBL  DC    (&RESMAX)CL65' ' SPECIAL RESOURCE NAME TBL       BC0327 X48491434
                                                                WC10076 48491534
* AUTPEDIT LINES TO BE INSERTED AS PART OF SETFORM/SETVAR CONV  BC10268 48491634
SFVL001  DC    C'//* %%SET %%0 = %%$CALCDTE %%$ODATE '          BC10268 48491734
SFVL002  DC    C'//* %%SET %%1 = %%SUBSTR %%0 1 2'              BC10268 48491834
SFVL003  DC    C'//* %%SET %%2 = %%SUBSTR %%0 3 2'              BC10268 48491934
SFVL004  DC    C'//* %%SET %%3 = %%SUBSTR %%0 5 2'              BC10268 48492034
SFVL005  DC    C'//* %%SET %%4 = %%SUBSTR %%0 7 2'              BC10268 48492134
SFVL006  DC    C'//* %%SET %%3 = %%SUBSTR %%$ODATE 1 2'         BC10268 48492234
SFVL007  DC    C'//* %%SET %%2 = %%SUBSTR %%$ODATE 3 2'         BC10268 48492334
SFVL008  DC    C'//* %%SET %%1 = %%SUBSTR %%$ODATE 5 2'         BC10268 48492434
SFVL009  DC    C'//* %%SET %%0 = %%3.%%2.%%1%%.01'              BC10268 48492534
SFVL010  DC    C'//* %%SET %%0 = %%$CALCDTE %%0 +M1'            BC10268 48492634
SFVL011  DC    C'//* %%SET %%0 = %%$WCALC %%0 -1 '              BC10268 48492734
SFVL012  DC    C'//* %%SET %%0 = %%$CALCDTE %%0 '               BC10268 48492834
SFVL013  DC    C'//* %%SET %%'                                  BC10268 48492934
SFVL014  DC    C'//* %%SET %%5 = %%$JULIAN %%0'                 BC10268 48493034
SFVL015  DC    C'//* %%SET %%6 = %%SUBSTR %%5 5 3'              BC10268 48493134
SFVL016  DC    C'//* %%SET %%0 = %%$WCALC %%$ODATE '            BC10268 48493234
SFVL017  DC    C'//* %%SET %%0 = %%$WCALC %%0 '                 BC10268 48493334
SFVL018  DC    C'//* %%SET %%0 = %%$CALCDTE %%$DATE '           BC10268 48493434
SFVL019  DC    C'//* %%SET %%0 = %%$CALCDTE %%0 -1'             BC10268 48493534
SFVL020  DC    C'//* %%SET %%0 = %%$WCALC %%0 > '               BC10268 48493634
SFVL021  DC    C'//* %%SET %%7 = %%$YEARWK# %%0'                BC10320 48493734
SFVL022  DC    C'//* %%SET %%8 = %%SUBSTR %%7 6 2'              BC10320 48493834
SFVL023  DC    C'//* %%SET %%0 = %%TIMEID'                      BC10320 48493934
SFVL024  DC    C'//* %%SET %%1 = %%SUBSTR %%0 1 2'              BC10320 48494034
SFVL025  DC    C'//* %%SET %%2 = %%SUBSTR %%0 3 2'              BC10320 48494134
SFVL026  DC    C'//* %%SET %%3 = %%SUBSTR %%0 5 2'              BC10320 48494234
SFVL027  DC    C'//* %%SET %%0 = %%$WCALC %%$DATE '             BC10320 48494334
SFVL028  DC    C'//* %%SET %%12345678 = %%SUBSTR &&' VAR+POS+LENBC10370 48494434
SFVDVADR DS    0H                                               BC10268 48494534
         DC    (SFVDVASN)CL(SFVDVELN)' '                        BC10320 48494634
SFVDVASK DS    0H                                               BC10320 48494734
         DC    CL(L'SFVDVNAM)'CYYYYMM',CL(L'SFVDVVAL)'CCYYMM'   BC10320 48494834
         DC    CL(L'SFVDVNAM)'CYYMMDD',CL(L'SFVDVVAL)'YYMMDD'   BC10320 48494934
         DC    CL(L'SFVDVNAM)'CYYMM',CL(L'SFVDVVAL)'YYMM'       BC10351 48495034
         DC    CL(L'SFVDVNAM)'CYYDDD',CL(L'SFVDVVAL)'YYDDD'     BC10351 48495134
         DC    CL(L'SFVDVNAM)'CMMYY',CL(L'SFVDVVAL)'MMYY'       BC10351 48495234
         DC    CL(L'SFVDVNAM)'CDDMMYY',CL(L'SFVDVVAL)'DDMMYY'   BC10351 48495334
         DC    CL(L'SFVDVNAM)'CYYYY',CL(L'SFVDVVAL)'CCYY'       BC10320 48495434
         DC    CL(L'SFVDVNAM)'OYYYY',CL(L'SFVDVVAL)'CCYY'       BC10320 48495534
         DC    CL(L'SFVDVNAM)'CYY',CL(L'SFVDVVAL)'YY'           BC10320 48495634
         DC    CL(L'SFVDVNAM)'CMM',CL(L'SFVDVVAL)'MM'           BC10320 48495734
         DC    CL(L'SFVDVNAM)'CWW',CL(L'SFVDVVAL)'WW' 2BYT WEEK#BC10320 48495834
         DC    CL(L'SFVDVNAM)'CYMD',CL(L'SFVDVVAL)'CCYYMMDD'    BC10320 48495934
         DC    CL(L'SFVDVNAM)'CDATE',CL(L'SFVDVVAL)'CCYYMMDD' ??BC10320 48496034
         DC    CL(L'SFVDVNAM)'OYYDDD',CL(L'SFVDVVAL)'YYDDD'     BC10320 48496134
         DC    CL(L'SFVDVNAM)'OYMD3',CL(L'SFVDVVAL)'YYYY/MM/DD' BC10351 48496234
         DC    CL(L'SFVDVNAM)'OYYMM',CL(L'SFVDVVAL)'YYMM'       BC10351 48496334
         DC    CL(L'SFVDVNAM)'ODMY2',CL(L'SFVDVVAL)'DD/MM/YY'   BC10320 48496434
         DC    CL(L'SFVDVNAM)'ODMY1',CL(L'SFVDVVAL)'DDMMYY'     BC10320 48496534
         DC    CL(L'SFVDVNAM)'OYMD1',CL(L'SFVDVVAL)'YYMMDD'     BC10320 48496634
         DC    CL(L'SFVDVNAM)'OYMD2',CL(L'SFVDVVAL)'YY/MM/DD'   BC10351 48496734
         DC    CL(L'SFVDVNAM)'OYMD3',CL(L'SFVDVVAL)'YYYY/MM/DD' BC10351 48496834
         DC    CL(L'SFVDVNAM)'OMMYY',CL(L'SFVDVVAL)'MMYY'       BC10320 48496934
         DC    CL(L'SFVDVNAM)'OCTIME',CL(L'SFVDVVAL)'HHMMSS'    BC10320 48497034
         DC    CL(L'SFVDVNAM)'CTIME',CL(L'SFVDVVAL)'HHMMSS'     BC10320 48497134
         DC    CL(L'SFVDVNAM)'CHHMM',CL(L'SFVDVVAL)'HHMM'       BC10351 48497234
         DC    CL(L'SFVDVNAM)'OYMD',CL(L'SFVDVVAL)'CCYYMMDD'    BC10268 48497334
         DC    CL(L'SFVDVNAM)'OYY',CL(L'SFVDVVAL)'YY'           BC10315 48497434
         DC    CL(L'SFVDVNAM)'OYM',CL(L'SFVDVVAL)'CCYYMM'       BC10268 48497534
         DC    CL(L'SFVDVNAM)'OMM',CL(L'SFVDVVAL)'MM'           BC10315 48497634
         DC    CL(L'SFVDVNAM)'ODD',CL(L'SFVDVVAL)'DD'           BC10351 48497734
         DC    CL(L'SFVDVNAM)'CDD',CL(L'SFVDVVAL)'DD'           BC10351 48497834
         DC    CL(L'SFVDVNAM)'CDDD',CL(L'SFVDVVAL)'DDD'      BC10448    48497934
         DC    CL(L'SFVDVNAM)'ODDD',CL(L'SFVDVVAL)'DDD'      BC10448    48498034
         DC    20CL(SFVDVELN)' '                                BC10268 48498134
SFVDVASE DS    0H                                               BC10320 48498234
SFVDVASN EQU   (SFVDVASE-SFVDVASK)/SFVDVELN                     BC10320 48498334
*TEMPLATE FOR WTO MESSAGE: SET VARIABLE NAME UNRESOLVED         BC10469 48498434
*BC10893 DC    H'84'                                            BC10469 48498534
*BC10893 DC    CL84'CTMOP1508W-XXXXXXXX SET STMT VARIABLE NAME UNRESOLV*48498634
               ED:                              '               BC10469 48498734
JSTABLE# EQU   500                                              BC10268 48499034
JSTABLE  DC    (JSTABLE#)CL(L'JSTVAR)' ' TABL TO HOLD SET VARS BC10268  48499134
JSTABLEL EQU   *-JSTABLE           LENGTH OF THE TABL           BC10268 48499234
CALNAMES DCB   DDNAME=CALNAMES,DSORG=PS,EODAD=CALEOD,MACRF=GL   BC10327 48499327
SIVARTAB DCB   DDNAME=DAVARTAB,DSORG=PS,EODAD=EOFJVAR,MACRF=GL,        *48499427
               DCBE=VARTABE                                     BC10278 48499527
VARTABE  DCBE  RMODE31=BUFF  31-BIT BUFF                        BC10278 48499627
APPLFILE DCB   DDNAME=DAAPPL,DSORG=PS,MACRF=GM,EODAD=EOFAPPL,          *48499727
               DCBE=APLDCBE                                     BC10278 48499827
APLDCBE  DCBE  RMODE31=BUFF  31-BIT BUFF                        BC10278 48499927
DSNTRAN  DCB   DDNAME=DSNTRAN,DSORG=PS,MACRF=GL,                       *48500034
               EODAD=DSNTEOF                                            48500134
INREC    DS    CL(APPLL)           AREA FOR APPL FILE RECORD    BC10278 48501027
SIAPOFFA DC    100CL(SIAPOFFL)' ' AREA FOR ENTRIES              BC10278 48520027
         AGO   .BFCHKAMP                                        BC10273 48530027
.ENDCODE ANOP                                                   BC10273 48540027
PARM     DSECT                                                          48541034
PMEMN    DS    A                                                        48542034
PMEMP    DS    A                                                        48543034
PLINE#   DS    A                                                        48544034
PWORK    DS    A                                                        48545034
PACTMMEM DS    A                                               WC0225   48546034
PMCTADDR DS    A                                               WC0367   48547034
PDCBERR  DS    A          ADDRESS OF DCB FOR ERR MSG           WC0467   48548034
CALNAMEA DS    A          ADDRESS OF 8 CHARS CALENDAR NAME      BC10327 48549034
SIAPOFF  DSECT                                                  BC10278 48549134
SIAOAPID DS    CL(L'OPAPPLID)                                   BC10278 48549234
SIAOPER  DS    CL(L'OPPERIOD)                                   BC10278 48549334
SIAO#SEQ DS    CL(L'OP#SEQNO)                                   BC10278 48549434
SIAOJVAR DS    CL(L'OPJCLVAR)                                   BC10278 48549534
SIAOOFF  DS    CL(24*L'OPOFFSET)                                BC10278 48549634
SIAPOFFL EQU   *-SIAPOFF                                        BC10278 48549734
SFVDV    DSECT ,       OPC DYNAMIC VARIABLES LIST               BC10268 48549849
SFVDVNAM DS    CL8     NAME OF DYNAMIC VARIABLE                 BC10268 48549949
SFVDVVAL DS    CL64    VALUE OF VARIABLE                        BC10268 48550049
SFVDVELN EQU   *-SFVDV ENTRY LENGTH                             BC10268 48551049
         END                                                            48560027
