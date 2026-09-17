"use client";

import { useEffect } from "react";
import { Upload } from "lucide-react";

import { DocumentTable } from "@/components/documents/document-table";
import { DocumentToolbar } from "@/components/documents/document-toolbar";
import { UploadDialog } from "@/components/documents/upload-dialog";
import { PageHeader, PageShell } from "@/components/layout/page-shell";
import { Button } from "@/components/ui/button";
import { useDocumentStore } from "@/store/use-document-store";

export default function DocumentsPage() {
  const total = useDocumentStore((state) => state.total);
  const load = useDocumentStore((state) => state.load);
  const setUploadOpen = useDocumentStore((state) => state.setUploadOpen);

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <PageShell>
      <div className="flex flex-col gap-5">
        <PageHeader
          title="文档管理"
          description="管理知识库来源，查看解析状态与实体抽取结果。"
          action={
            <Button onClick={() => setUploadOpen(true)}>
              <Upload className="size-4" />
              上传文档
            </Button>
          }
        />

        <DocumentToolbar total={total} />
        <DocumentTable />
      </div>

      <UploadDialog />
    </PageShell>
  );
}
