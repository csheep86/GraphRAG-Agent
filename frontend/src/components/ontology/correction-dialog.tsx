"use client";

import { useMemo, useState } from "react";
import { Loader2, Plus, TriangleAlert, X } from "lucide-react";

import type { OntologyCandidate } from "@/api/ontology";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  useOntologyStore,
  type CorrectionAction,
} from "@/store/use-ontology-store";

const ACTION_TITLE = {
  merge: "合并实体",
  rename: "改实体规范名",
  split: "拆分实体",
} as const;

const ACTION_DESCRIPTION = {
  merge: "被并入侧的实体不再独立存在；属性并入保留侧，关系按原方向重挂。",
  rename: "旧规范名会写入 aliases（后端负责），历史证据仍能对得上人。",
  split: "只填新实体的规范名（≥2 个）；关系迁移由后端按「默认同名」规则处理。",
} as const;

/**
 * 三动作弹窗（m6 §1.2：只做**单条**校正，不做批量 / 撤销栈 / 版本对比）。
 *
 * **实体来源只有候选行**（proposal P5I-4）：不另造实体搜索端点，
 * rename / split 在「保留侧 / 被并入侧」之间二选一。
 *
 * **为什么表单单独成一个组件**：靠父级给它一个 `key`（动作 + 候选 id），
 * 每次换动作 / 换候选就**整体重挂载**，草稿自然清空 —— 比在 effect 里
 * setState 更符合 React 惯例（lint 规则 `react-hooks/set-state-in-effect`
 * 明确禁止后者：会触发级联渲染）。
 */
export function CorrectionDialog() {
  const dialog = useOntologyStore((state) => state.dialog);
  const closeDialog = useOntologyStore((state) => state.closeDialog);
  const submitting = useOntologyStore((state) => state.submitting);

  return (
    <Dialog
      open={dialog !== null}
      onOpenChange={(next) => {
        if (submitting) return;
        if (!next) closeDialog();
      }}
    >
      <DialogContent className="max-w-lg">
        {dialog ? (
          <CorrectionForm
            key={`${dialog.action}:${dialog.candidate.id}`}
            action={dialog.action}
            candidate={dialog.candidate}
          />
        ) : null}
      </DialogContent>
    </Dialog>
  );
}

function CorrectionForm({
  action,
  candidate,
}: {
  action: CorrectionAction;
  candidate: OntologyCandidate;
}) {
  const closeDialog = useOntologyStore((state) => state.closeDialog);
  const submitting = useOntologyStore((state) => state.submitting);
  const actionError = useOntologyStore((state) => state.actionError);
  const submitMerge = useOntologyStore((state) => state.submitMerge);
  const submitRename = useOntologyStore((state) => state.submitRename);
  const submitSplit = useOntologyStore((state) => state.submitSplit);

  const [target, setTarget] = useState<"left" | "right">("left");
  const [newName, setNewName] = useState("");
  const [names, setNames] = useState<string[]>(["", ""]);
  const [localError, setLocalError] = useState<string | null>(null);

  const targetEntityId = useMemo(
    () =>
      target === "left" ? candidate.left_entity_id : candidate.right_entity_id,
    [candidate, target],
  );

  const handleSubmit = async () => {
    setLocalError(null);

    if (action === "merge") {
      await submitMerge(candidate);
      return;
    }

    if (action === "rename") {
      if (newName.trim().length === 0) {
        setLocalError("新规范名不能为空");
        return;
      }
      await submitRename(targetEntityId, newName.trim());
      return;
    }

    const trimmed = names
      .map((name) => name.trim())
      .filter((name) => name.length > 0);
    if (trimmed.length < 2) {
      setLocalError("至少填 2 个新实体名——只拆出 1 个等价改名，应走「改名」");
      return;
    }
    await submitSplit(targetEntityId, trimmed);
  };

  return (
    <>
      <DialogHeader>
        <DialogTitle>{ACTION_TITLE[action]}</DialogTitle>
        <DialogDescription>{ACTION_DESCRIPTION[action]}</DialogDescription>
      </DialogHeader>

      <div className="flex flex-col gap-3">
        <div className="rounded-lg border border-border bg-foreground/[0.02] p-3 text-[11px] leading-relaxed text-muted-foreground">
          <div>
            保留侧：<span className="font-mono">{candidate.left_entity_id}</span>
          </div>
          <div>
            被并入侧：
            <span className="font-mono">{candidate.right_entity_id}</span>
          </div>
          <div>相似度：{candidate.similarity.toFixed(2)}</div>
        </div>

        {action === "merge" ? null : (
          <div className="flex flex-col gap-1.5">
            <span className="text-xs text-muted-foreground">
              作用于哪个实体
            </span>
            <div className="flex items-center gap-2">
              <Button
                variant={target === "left" ? "secondary" : "outline"}
                size="xs"
                onClick={() => setTarget("left")}
                disabled={submitting}
              >
                保留侧
              </Button>
              <Button
                variant={target === "right" ? "secondary" : "outline"}
                size="xs"
                onClick={() => setTarget("right")}
                disabled={submitting}
              >
                被并入侧
              </Button>
            </div>
            <p className="font-mono text-[11px] text-muted-foreground">
              {targetEntityId}
            </p>
          </div>
        )}

        {action === "rename" ? (
          <div className="flex flex-col gap-1.5">
            <label
              htmlFor="new-canonical-name"
              className="text-xs text-muted-foreground"
            >
              新规范名
            </label>
            <input
              id="new-canonical-name"
              value={newName}
              onChange={(event) => setNewName(event.target.value)}
              disabled={submitting}
              placeholder="例：甲有限公司"
              className="h-9 w-full rounded-lg border border-border bg-transparent px-3 text-[13px] text-foreground outline-none transition-colors focus:border-primary/60"
            />
          </div>
        ) : null}

        {action === "split" ? (
          <div className="flex flex-col gap-1.5">
            <span className="text-xs text-muted-foreground">
              新实体规范名（≥2）
            </span>
            {names.map((name, index) => (
              <div key={index} className="flex items-center gap-2">
                <input
                  value={name}
                  onChange={(event) => {
                    const next = [...names];
                    next[index] = event.target.value;
                    setNames(next);
                  }}
                  disabled={submitting}
                  placeholder={`新实体 ${index + 1}`}
                  aria-label={`新实体 ${index + 1}`}
                  className="h-9 w-full rounded-lg border border-border bg-transparent px-3 text-[13px] text-foreground outline-none transition-colors focus:border-primary/60"
                />
                {names.length > 2 ? (
                  <Button
                    variant="ghost"
                    size="icon-xs"
                    aria-label="删除该行"
                    disabled={submitting}
                    onClick={() => setNames(names.filter((_, i) => i !== index))}
                  >
                    <X className="size-3.5" />
                  </Button>
                ) : null}
              </div>
            ))}
            <Button
              variant="ghost"
              size="xs"
              className="w-fit"
              disabled={submitting}
              onClick={() => setNames([...names, ""])}
            >
              <Plus className="size-3.5" />
              再加一个
            </Button>
          </div>
        ) : null}

        {localError || actionError ? (
          <p
            className="flex items-start gap-1.5 text-xs text-destructive"
            role="alert"
          >
            <TriangleAlert className="mt-0.5 size-3.5 shrink-0" />
            {localError ?? actionError}
          </p>
        ) : null}
      </div>

      <DialogFooter>
        <Button variant="ghost" onClick={closeDialog} disabled={submitting}>
          取消
        </Button>
        <Button onClick={() => void handleSubmit()} disabled={submitting}>
          {submitting ? <Loader2 className="size-4 animate-spin" /> : null}
          {submitting ? "执行中…" : "确认执行"}
        </Button>
      </DialogFooter>
    </>
  );
}
