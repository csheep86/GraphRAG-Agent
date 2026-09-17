/**
 * 轻量力导向布局（Fruchterman–Reingold 变体），零依赖。
 *
 * 说明：p04 设计稿给出了明确的节点相对位置，因此这里在标准「斥力 + 边引力」
 * 之外追加了一个**弱锚点回拉**，让模拟收敛在设计稿布局附近，
 * 既保留力导向的真实物理过程，又能稳定还原视觉稿。
 *
 * 全部计算基于固定 viewBox 尺寸、且伪随机数由节点序号推导，
 * 因此 SSR 与 CSR 结果完全一致（不会触发 hydration 不匹配）。
 */

export type LayoutInputNode = {
  id: string;
  /** 0–1 归一化种子坐标 */
  seed_x: number;
  seed_y: number;
};

export type LayoutInputEdge = {
  source: string;
  target: string;
};

export type PositionedNode = {
  id: string;
  x: number;
  y: number;
};

export type ForceLayoutOptions = {
  iterations?: number;
  padding?: number;
  /** 锚点回拉强度 0–1，越大越贴近设计稿布局 */
  anchorStrength?: number;
};

function pseudoRandom(seed: number): number {
  const x = Math.sin(seed * 12.9898) * 43758.5453;
  return x - Math.floor(x);
}

function clamp(value: number, min: number, max: number): number {
  return Math.min(Math.max(value, min), max);
}

type Particle = {
  id: string;
  x: number;
  y: number;
  /** 锚点（设计稿位置） */
  ax: number;
  ay: number;
};

export function computeForceLayout(
  nodes: LayoutInputNode[],
  edges: LayoutInputEdge[],
  width: number,
  height: number,
  options: ForceLayoutOptions = {},
): PositionedNode[] {
  const { iterations = 140, padding = 78, anchorStrength = 0.85 } = options;
  const count = nodes.length;
  if (count === 0) return [];

  const innerWidth = Math.max(width - padding * 2, 1);
  const innerHeight = Math.max(height - padding * 2, 1);

  const particles: Particle[] = nodes.map((node, index) => {
    const jitterX = (pseudoRandom(index * 2 + 1) - 0.5) * 10;
    const jitterY = (pseudoRandom(index * 2 + 2) - 0.5) * 10;
    const ax = padding + node.seed_x * innerWidth;
    const ay = padding + node.seed_y * innerHeight;

    return { id: node.id, x: ax + jitterX, y: ay + jitterY, ax, ay };
  });

  const byId = new Map(particles.map((particle) => [particle.id, particle]));

  // 理想边长
  const k = Math.sqrt((innerWidth * innerHeight) / count);

  for (let step = 0; step < iterations; step += 1) {
    // 1) 节点间斥力（Coulomb）
    for (let i = 0; i < particles.length; i += 1) {
      for (let j = i + 1; j < particles.length; j += 1) {
        const a = particles[i];
        const b = particles[j];

        let dx = a.x - b.x;
        let dy = a.y - b.y;
        let distance = Math.hypot(dx, dy);
        if (distance < 0.01) {
          dx = 0.01;
          dy = 0.01;
          distance = 0.01;
        }

        const force = (k * k) / distance;
        const fx = (dx / distance) * force;
        const fy = (dy / distance) * force;

        a.x += fx;
        a.y += fy;
        b.x -= fx;
        b.y -= fy;
      }
    }

    // 2) 边的弹簧引力（Hooke）
    for (const edge of edges) {
      const a = byId.get(edge.source);
      const b = byId.get(edge.target);
      if (!a || !b) continue;

      const dx = a.x - b.x;
      const dy = a.y - b.y;
      const distance = Math.hypot(dx, dy) || 0.01;

      const force = ((distance * distance) / k) * 0.02;
      const fx = (dx / distance) * force;
      const fy = (dy / distance) * force;

      a.x -= fx;
      a.y -= fy;
      b.x += fx;
      b.y += fy;
    }

    // 3) 弱锚点回拉 + 边界收敛
    for (const particle of particles) {
      particle.x += (particle.ax - particle.x) * anchorStrength * 0.16;
      particle.y += (particle.ay - particle.y) * anchorStrength * 0.16;
      particle.x = clamp(particle.x, padding * 0.45, width - padding * 0.45);
      particle.y = clamp(particle.y, padding * 0.35, height - padding * 0.35);
    }
  }

  return particles.map((particle) => ({
    id: particle.id,
    x: Math.round(particle.x * 100) / 100,
    y: Math.round(particle.y * 100) / 100,
  }));
}
