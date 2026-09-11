@echo off
chcp 65001 >nul
echo ======================================================
echo    Instalador do Certificado Oficial: alexdoong
echo ======================================================
echo.
echo Registrando alexdoong como Fornecedor Confiavel no Windows...
echo.

certutil -addstore -user Root "%~dp0alexdoong.cer"
if %ERRORLEVEL% EQU 0 (
    echo.
    echo ======================================================
    echo  [SUCESSO] Certificado instalado com exito!
    echo  O Windows agora reconhece "alexdoong" como
    echo  Fornecedor Verificado do Xennex.
    echo ======================================================
) else (
    echo.
    echo [ERRO] Nao foi possivel registrar o certificado.
)

pause
