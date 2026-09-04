"use client";
import { useEffect, useRef } from "react";

interface Props { active: boolean; risk: "low" | "medium" | "high"; }

export default function MiniWaveform({ active, risk }: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const frameRef  = useRef<number>(0);
  const phaseRef  = useRef<number>(Math.random() * Math.PI * 2);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    canvas.width  = canvas.offsetWidth  * window.devicePixelRatio;
    canvas.height = canvas.offsetHeight * window.devicePixelRatio;
    ctx.scale(window.devicePixelRatio, window.devicePixelRatio);

    const color = risk === "high" ? "#e8394a" : risk === "medium" ? "#f0a500" : "#00d4aa";

    const draw = () => {
      const W = canvas.offsetWidth;
      const H = canvas.offsetHeight;
      ctx.clearRect(0, 0, W, H);
      ctx.beginPath();
      ctx.strokeStyle = color;
      ctx.lineWidth = 1.2;
      ctx.globalAlpha = active ? 0.8 : 0.3;

      const pts = 80;
      const amp = active ? H * 0.35 : H * 0.08;
      const phase = phaseRef.current;

      for (let i = 0; i <= pts; i++) {
        const x = (i / pts) * W;
        const t = (i / pts) * Math.PI * 4 + phase;
        const y = H / 2 + Math.sin(t) * amp + Math.sin(t * 2.5) * amp * 0.3;
        if (i === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
      }
      ctx.stroke();
      ctx.globalAlpha = 1;
      phaseRef.current += active ? 0.04 : 0.008;
      frameRef.current = requestAnimationFrame(draw);
    };

    frameRef.current = requestAnimationFrame(draw);
    return () => cancelAnimationFrame(frameRef.current);
  }, [active, risk]);

  return <canvas ref={canvasRef} className="mini-waveform" />;
}
