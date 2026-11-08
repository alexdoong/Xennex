@echo off
chcp 65001 >nul
echo ======================================================
echo    Certificado autoassinado: alexdoong
echo ======================================================
echo.
echo Esta etapa e opcional: o Xennex funciona sem instalar este certificado.
echo A instalacao amplia a confianca do usuario atual em arquivos assinados
echo por esta chave. Nao impede malware nem garante reputacao SmartScreen.
choice /C SN /N /M "Deseja adicionar esta raiz confiavel? [S/N] "
if errorlevel 2 exit /b 0
echo Registrando a raiz de confianca do usuario atual...
echo.

certutil -addstore -user Root "%~dp0alexdoong.cer"
if %ERRORLEVEL% EQU 0 (
    echo.
    echo ======================================================
    echo  [SUCESSO] Certificado instalado com exito!
    echo  Certificado autoassinado adicionado para este usuario.
    echo  Essa confianca tambem se aplica a outros arquivos da mesma chave.
    echo ======================================================
) else (
    echo.
    echo [ERRO] Nao foi possivel registrar o certificado.
)

pause
