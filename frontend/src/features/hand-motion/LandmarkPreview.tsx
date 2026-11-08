const chains = [[0,1,2,3,4], [0,5,6,7,8], [5,9,10,11,12], [9,13,14,15,16], [13,17,18,19,20], [17,0]];
export function LandmarkPreview({ points }: { points?: number[][] }) {
  return <div className="gestures-preview">
    {points?.length === 21 ? <svg viewBox="0 0 640 480" role="img" aria-label="Pontos da mão detectada">
      {chains.map((chain, i) => <polyline key={i} points={chain.map(index => `${points[index][0] * 640},${points[index][1] * 480}`).join(' ')} />)}
      {points.map((p, i) => <circle key={i} cx={p[0] * 640} cy={p[1] * 480} r={i === 4 || i === 8 ? 7 : 4} />)}
    </svg> : <p>Os 21 pontos da mão aparecerão aqui.<br />Mantenha a mão inteira diante da câmera.</p>}
  </div>;
}
