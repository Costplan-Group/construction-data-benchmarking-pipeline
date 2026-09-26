import { Editor } from "@tinymce/tinymce-react";
import "tinymce/tinymce";
import "tinymce/icons/default";
import "tinymce/themes/silver";
import "tinymce/models/dom";
import "tinymce/plugins/lists";
import "tinymce/plugins/link";
import "tinymce/plugins/table";
import "tinymce/plugins/code";
import "tinymce/skins/ui/oxide/skin.min.css";
import "tinymce/skins/content/default/content.min.css";

type RichTextEditorProps = {
  id: string;
  value: string;
  height?: number;
  onChange: (value: string) => void;
  compact?: boolean;
};

export function RichTextEditor({
  id,
  value,
  height = 220,
  onChange,
  compact = false,
}: RichTextEditorProps) {
  return (
    <Editor
      id={id}
      value={value}
      onEditorChange={onChange}
      init={{
        licenseKey: "gpl",
        height,
        menubar: false,
        branding: false,
        plugins: compact ? ["lists", "link"] : ["lists", "link", "table", "code"],
        toolbar: compact
          ? "undo redo | blocks | bold italic underline | bullist numlist | link"
          : "undo redo | blocks | bold italic underline | bullist numlist | table | link | code",
      }}
    />
  );
}
