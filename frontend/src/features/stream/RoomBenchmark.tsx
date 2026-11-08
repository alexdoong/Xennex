import { useEffect, useState, type MutableRefObject } from 'react';
import { SessionBenchmark } from './sessionBenchmark';

export default function RoomBenchmark({ current }: { current: MutableRefObject<SessionBenchmark | undefined> }) {
  const [duration, setDuration] = useState<60 | 900>(60);
  const [remaining, setRemaining] = useState(0);
  const [report, setReport] = useState('');
  const [notice, setNotice] = useState('');
  useEffect(() => {
    const timer = setInterval(() => {
      const benchmark = current.current;
      if (!benchmark) return;
      setRemaining(benchmark.secondsRemaining);
      if (!benchmark.active) { benchmark.stop(); setReport(JSON.stringify(benchmark.report(), null, 2)); current.current = undefined; }
    }, 1000);
    return () => { clearInterval(timer); current.current?.stop(); current.current = undefined; };
  }, [current]);
  const finish = () => {
    if (!current.current) return;
    current.current.stop(); setReport(JSON.stringify(current.current.report(), null, 2)); current.current = undefined; setRemaining(0);
  };
  const copy = async () => {
    try { await navigator.clipboard.writeText(report); setNotice('Relatório copiado.'); }
    catch { setNotice('Selecione e copie o relatório abaixo.'); }
  };
  return <details className="room-benchmark"><summary>Medir esta sessão</summary>
    <p>Separa chegada de quadros, encode/decode e registra foco/aba oculta. O navegador pode reduzir renderização ou timers em segundo plano; FPS exibidos não comprovam a taxa enviada. Não captura nem salva imagens e não envia o relatório. CPU/GPU, captura bruta e latência ponta a ponta precisam de ensaios próprios.</p>
    <label>Duração da medição<select value={duration} disabled={remaining > 0} onChange={event => setDuration(Number(event.target.value) === 900 ? 900 : 60)}><option value={60}>1 minuto</option><option value={900}>15 minutos</option></select></label>
    <button disabled={remaining > 0} onClick={() => { current.current = new SessionBenchmark(duration); setRemaining(duration); setReport(''); setNotice(''); }}>Iniciar medição</button>
    {remaining > 0 && <><span role="status">Medindo · {remaining}s restantes</span><button onClick={finish}>Encerrar medição</button></>}
    {report && <><button onClick={() => void copy()}>Copiar relatório da medição</button>
      <pre tabIndex={0}>{report}</pre></>}
    {notice && <p role="status">{notice}</p>}
  </details>;
}
