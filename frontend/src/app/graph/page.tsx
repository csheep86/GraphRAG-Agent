"use client";

import { useEffect } from "react";
import { Maximize2, ZoomIn, ZoomOut } from "lucide-react";

import { EntityDetailPanel } from "@/components/graph/entity-detail-panel";
import { GraphCanvas } from "@/components/graph/graph-canvas";
import { Button } from "@/components/ui/button";
import { useGraphStore } from "@/store/use-graph-store";

export default function GraphPage() {
  const load = useGraphStore((state) => state.load);
  const zoomIn = useGraphStore((state) => state.zoomIn);
  const zoomOut = useGraphStore((state) => state.zoomOut);
  const resetZoom = useGraphStore((state) => state.resetZoom);

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-3 p-6">
      {/* 图控制：放大 / 缩小 / 适应视图 */}
      <div className="flex items-center justify-end gap-1">
        <Button variant="ghost" size="icon-sm" onClick={zoomIn} aria-label="放大">
          <ZoomIn className="size-4" />
        </Button>
        <Button variant="ghost" size="icon-sm" onClick={zoomOut} aria-label="缩小">
          <ZoomOut className="size-4" />
        </Button>
        <Button
          variant="ghost"
          size="icon-sm"
          onClick={resetZoom}
          aria-label="适应视图"
        >
          <Maximize2 className="size-4" />
        </Button>
      </div>

      <div className="grid min-h-0 flex-1 grid-cols-[minmax(0,1fr)_300px] gap-4">
        <GraphCanvas />
        <EntityDetailPanel />
      </div>
    </div>
  );
}
