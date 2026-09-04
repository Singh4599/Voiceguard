"use client";
import { useEffect, useRef } from "react";

interface Props {
  chunks: { is_clone: boolean; confidence: number }[];
  active: boolean;
}

export default function Oscilloscope({ chunks, active }: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const frameRef = useRef<number>(0);
  const phaseRef = useRef<number>(0);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const resize = () => {
      canvas.width  = canvas.offsetWidth  * window.devicePixelRatio;
      canvas.height = canvas.offsetHeight * window.devicePixelRatio;
      ctx.scale(window.devicePixelRatio, window.devicePixelRatio);
    };
    resize();
    window.addEventListener("resize", resize);

    // Pick color based on latest chunk
    const latestConf = chunks.length > 0 ? chunks[chunks.length - 1].confidence : 0;
    const isClone = chunks.length > 0 && chunks[chunks.length - 1].is_clone;

    const getColor = () => {
      if (!active) return "#4a5260";
      if (isClone && latestConf > 0.7) return "#e8394a";
      if (latestConf > 0.4) return "#f0a500";
      return "#00d4aa";
    };

    let phase = phaseRef.current;

    const draw = () => {
      const W = canvas.offsetWidth;
      const H = canvas.offsetHeight;
      ctx.clearRect(0, 0, W, H);

      // Grid lines
      ctx.strokeStyle = "#1e222b";
      ctx.lineWidth = 0.5;
      for (let i = 1; i < 4; i++) {
        ctx.beginPath();
        ctx.moveTo(0, (H / 4) * i);
        ctx.lineTo(W, (H / 4) * i);
        ctx.stroke();
      }
      for (let i = 1; i < 8; i++) {
        ctx.beginPath();
        ctx.moveTo((W / 8) * i, 0);
        ctx.lineTo((W / 8) * i, H);
        ctx.stroke();
      }

      const color = getColor();
      const amplitude = active ? (isClone ? 0.38 : 0.22) : 0.06;

      // Glow effect
      if (active) {
        ctx.shadowColor = color;
        ctx.shadowBlur = isClone ? 8 : 4;
      }

      ctx.beginPath();
      ctx.strokeStyle = color;
      ctx.lineWidth = 1.5;

      const points = 300;
      for (let i = 0; i <= points; i++) {
        const x = (i / points) * W;
        const t = (i / points) * Math.PI * 6 + phase;

        // Composite waveform — more complex = more "real" looking
        const y =
          H / 2 +
          Math.sin(t) * amplitude * H +
          Math.sin(t * 2.3 + 0.5) * amplitude * 0.4 * H +
          Math.sin(t * 5.1 + 1.2) * amplitude * 0.15 * H +
          (active ? (Math.random() - 0.5) * amplitude * 0.3 * H : 0);

        if (i === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
      }
      ctx.stroke();
      ctx.shadowBlur = 0;

      phase += active ? (isClone ? 0.06 : 0.03) : 0.005;
      phaseRef.current = phase;
      frameRef.current = requestAnimationFrame(draw);
    };

    frameRef.current = requestAnimationFrame(draw);

    return () => {
      cancelAnimationFrame(frameRef.current);
      window.removeEventListener("resize", resize);
    };
  }, [chunks, active]);

  return <canvas ref={canvasRef} className="oscilloscope-canvas" />;
}
