"use client";

import { useEffect, useMemo, useRef, useState } from "react";

import { Card, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { computeForceLayout } from "@/lib/force-layout";
import { formatNumber } from "@/lib/format";
import { cn } from "@/lib/utils";
import { useGraphStore } from "@/store/use-graph-store";

import { CATEGORY_COLOR_VAR, GraphLegend } from "./graph-legend";

const EDGE_IDLE = "#33333f";
const EDGE_ACTIVE = "#4b7bff";

export function GraphCanvas() {
  const overview = useGraphStore((state) => state.overview);
  const loading = useGraphStore((state) => state.loading);
  const selectedId = useGraphStore((state) => state.selectedId);
  const select = useGraphStore((state) => state.select);
  const zoom = useGraphStore((state) => state.zoom);

  const containerRef = useRef<HTMLDivElement>(null);
  const [size, setSize] = useState({ width: 0, height: 0 });
  const [offset, setOffset] = useState({ x: 0, y: 0 });
  const [dragging, setDragging] = useState(false);
  const dragRef = useRef<{
    startX: number;
    startY: number;
    originX: number;
    originY: number;
    moved: boolean;
  } | null>(null);

  // 画布尺寸在客户端测量：SVG 用真实像素坐标系渲染，字号/半径与设计稿 1:1
  useEffect(() => {
    const element = containerRef.current;
    if (!element) return;

    const observer = new ResizeObserver((entries) => {
      const rect = entries[0]?.contentRect;
      if (!rect) return;
      setSize({
        width: Math.round(rect.width),
        height: Math.round(rect.height),
      });
    });

    observer.observe(element);
    return () => observer.disconnect();
  }, []);

  const layout = useMemo(() => {
    if (!overview || size.width === 0 || size.height === 0) return [];
    return computeForceLayout(overview.nodes, overview.edges, size.width, size.height, {
      padding: 92,
    });
  }, [overview, size.width, size.height]);

  const positions = useMemo(
    () => new Map(layout.map((node) => [node.id, node])),
    [layout],
  );

  const viewBox = useMemo(() => {
    if (size.width === 0 || size.height === 0) return "0 0 1 1";
    const width = size.width / zoom;
    const height = size.height / zoom;
    const x = size.width / 2 - width / 2 - offset.x;
    const y = size.height / 2 - height / 2 - offset.y;
    return `${x} ${y} ${width} ${height}`;
  }, [size.width, size.height, zoom, offset.x, offset.y]);

  const handlePointerDown = (event: React.PointerEvent<SVGSVGElement>) => {
    dragRef.current = {
      startX: event.clientX,
      startY: event.clientY,
      originX: offset.x,
      originY: offset.y,
      moved: false,
    };
    setDragging(true);
  };

  const handlePointerMove = (event: React.PointerEvent<SVGSVGElement>) => {
    const drag = dragRef.current;
    if (!drag) return;

    const deltaX = event.clientX - drag.startX;
    const deltaY = event.clientY - drag.startY;

    if (!drag.moved && Math.hypot(deltaX, deltaY) > 3) drag.moved = true;
    if (!drag.moved) return;

    setOffset({
      x: drag.originX + deltaX / zoom,
      y: drag.originY + deltaY / zoom,
    });
  };

  const handlePointerUp = () => {
    setDragging(false);
    // 保留 moved 标记到下一次 pointerdown，避免拖拽结束误触发节点点击
    setTimeout(() => {
      if (dragRef.current) dragRef.current.moved = false;
    }, 0);
  };

  const handleNodeClick = (entityId: string) => {
    if (dragRef.current?.moved) return;
    select(entityId);
  };

  return (
    <Card className="flex h-full min-h-0 min-w-0 flex-col gap-0 overflow-hidden">
      <CardHeader className="px-5 pt-4 pb-3">
        <CardTitle>知识图谱 · 全部实体</CardTitle>
        <p className="text-[11px] text-muted-foreground">
          {overview
            ? `${formatNumber(overview.doc_count)} 份文档 · ${formatNumber(overview.entity_count)} 个实体 · ${formatNumber(overview.relation_count)} 条关系`
            : "--"}
        </p>
      </CardHeader>

      <div ref={containerRef} className="relative min-h-0 flex-1">
        {loading || size.width === 0 || !overview ? (
          <div className="absolute inset-0 flex items-center justify-center">
            <Skeleton className="h-2/3 w-3/4 rounded-full opacity-40" />
          </div>
        ) : (
          <svg
            width={size.width}
            height={size.height}
            viewBox={viewBox}
            role="img"
            aria-label="知识图谱力导向图"
            className={cn(
              "touch-none select-none",
              dragging ? "cursor-grabbing" : "cursor-grab",
            )}
            onPointerDown={handlePointerDown}
            onPointerMove={handlePointerMove}
            onPointerUp={handlePointerUp}
            onPointerLeave={handlePointerUp}
          >
            {/* 边 */}
            <g>
              {overview.edges.map((edge) => {
                const source = positions.get(edge.source);
                const target = positions.get(edge.target);
                if (!source || !target) return null;

                const active =
                  selectedId === edge.source || selectedId === edge.target;

                return (
                  <line
                    key={edge.id}
                    x1={source.x}
                    y1={source.y}
                    x2={target.x}
                    y2={target.y}
                    stroke={active ? EDGE_ACTIVE : EDGE_IDLE}
                    strokeWidth={active ? 1.6 : 1}
                  />
                );
              })}
            </g>

            {/* 节点 + 标签 */}
            <g>
              {overview.nodes.map((node) => {
                const position = positions.get(node.id);
                if (!position) return null;

                const radius = 11 + node.weight * 4;
                const active = selectedId === node.id;
                const color = CATEGORY_COLOR_VAR[node.category];

                return (
                  <g
                    key={node.id}
                    className="cursor-pointer"
                    onClick={() => handleNodeClick(node.id)}
                  >
                    {active ? (
                      <circle
                        cx={position.x}
                        cy={position.y}
                        r={radius + 7}
                        fill={color}
                        opacity={0.18}
                      />
                    ) : null}

                    <circle
                      cx={position.x}
                      cy={position.y}
                      r={radius}
                      fill={color}
                    />

                    <text
                      x={position.x + radius + 10}
                      y={position.y - 1}
                      fill="#f4f4f6"
                      fontSize={13}
                      fontWeight={500}
                    >
                      {node.name}
                    </text>
                    <text
                      x={position.x + radius + 10}
                      y={position.y + 13}
                      fill="#8b8b98"
                      fontSize={10}
                    >
                      {node.type}
                    </text>
                  </g>
                );
              })}
            </g>
          </svg>
        )}

        <GraphLegend />
      </div>
    </Card>
  );
}
