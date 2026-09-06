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

      // Build a waveform that reflects actual confidence data from chunks
      // Each chunk's confidence drives the amplitude in its segment
      const numChunks = Math.max(chunks.length, 1);
      const latestConf = chunks.length > 0 ? chunks[chunks.length - 1].confidence : 0;
      const isClone = chunks.length > 0 && chunks[chunks.length - 1].is_clone;

      // Color based on real latest confidence
      let color = "#00d4aa"; // green = real
      if (!active) {
        color = "#4a5260";
      } else if (isClone && latestConf > 0.7) {
        color = "#e8394a"; // red = AI clone
      } else if (latestConf > 0.4) {
        color = "#f0a500"; // amber = suspicious
      }

      // Glow
      if (active) {
        ctx.shadowColor = color;
        ctx.shadowBlur = isClone ? 8 : 4;
      }

      ctx.beginPath();
      ctx.strokeStyle = color;
      ctx.lineWidth = 1.5;

      const points = 400;
      for (let i = 0; i <= points; i++) {
        const x = (i / points) * W;
        const t = (i / points) * Math.PI * 6 + phase;

        // Map x-position to the corresponding chunk index
        const chunkIdx = Math.min(Math.floor((i / points) * numChunks), numChunks - 1);
        const chunkConf = chunks[chunkIdx]?.confidence ?? 0;

        // Amplitude driven by the chunk's confidence value
        // Higher confidence = higher amplitude (more agitated signal)
        const baseAmp = active ? 0.12 : 0.04;
        const confAmp = chunkConf * 0.3; // confidence scales 0..0.3
        const amplitude = baseAmp + confAmp;

        // Composite waveform using chunk data as seed
        const y =
          H / 2 +
          Math.sin(t) * amplitude * H +
          Math.sin(t * 2.3 + chunkConf * 5) * amplitude * 0.35 * H +
          Math.sin(t * 4.7 + chunkConf * 10) * amplitude * 0.15 * H +
          (active ? (Math.random() - 0.5) * amplitude * 0.2 * H : 0);

        if (i === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
      }
      ctx.stroke();
      ctx.shadowBlur = 0;

      phase += active ? (isClone ? 0.05 : 0.025) : 0.003;
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
