$ErrorActionPreference = 'Stop'
$taskRoot = Split-Path -Parent $PSScriptRoot
$taskFixtures = Join-Path $taskRoot '.cache\voice-fixtures'
New-Item -ItemType Directory -Force -Path $taskFixtures | Out-Null
$taskVoice = New-Object -ComObject SAPI.SpVoice
$taskPortuguese = @($taskVoice.GetVoices() | Where-Object { $_.GetAttribute('Language') -eq '416' })
if ($taskPortuguese.Count -eq 0) { throw 'A voz local pt-BR do Windows não está instalada.' }
$taskVoice.Voice = $taskPortuguese[0]
$taskVoice.Rate = 0
$taskTexts = @(
    'Computador, ativar.', 'Computador, pausar.', 'Computador, retomar.',
    'Computador, abrir configurações.', 'Computador, iniciar ditado.',
    'Computador, terminar ditado.', 'Computador, continuar ditado.',
    'Computador, clicar.', 'Computador, clique duplo.', 'Computador, clique direito.',
    'Computador, rolar para baixo.', 'Computador, abrir navegador.',
    'Computador, abrir bloco de notas.', 'Computador, abrir calculadora.',
    'Computador, alternar janela.', 'Computador, copiar.', 'Computador, colar.',
    'Computador, apagar última palavra.', 'Computador, vírgula.',
    'Computador, encerrar controle.',
    'Vou usar o computador para escrever um texto.',
    'Hoje vamos conversar sobre matemática e educação.',
    'A ação foi concluída com atenção. Amanhã teremos uma nova reunião.'
)
$taskCases = @()
for ($taskIndex = 0; $taskIndex -lt $taskTexts.Count; $taskIndex++) {
    $taskFilename = '{0:D2}.wav' -f $taskIndex
    $taskStream = New-Object -ComObject SAPI.SpFileStream
    $taskStream.Format.Type = 18
    $taskStream.Open((Join-Path $taskFixtures $taskFilename), 3, $false)
    $taskVoice.AudioOutputStream = $taskStream
    [void]$taskVoice.Speak($taskTexts[$taskIndex])
    $taskStream.Close()
    $taskCases += [pscustomobject]@{file=$taskFilename; text=$taskTexts[$taskIndex]}
}
$taskCases | ConvertTo-Json | Set-Content -Encoding UTF8 -LiteralPath (Join-Path $taskFixtures 'cases.json')
Write-Output "Prepared $($taskCases.Count) synthetic voice fixtures."

