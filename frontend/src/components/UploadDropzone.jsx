import { useState, useRef } from 'react'
import { UploadCloud, FileSpreadsheet, Loader2 } from 'lucide-react'

export default function UploadDropzone({ onUpload, uploading }) {
  const [dragActive, setDragActive] = useState(false)
  const inputRef = useRef()

  const handleFiles = (files) => {
    if (files && files[0]) onUpload(files[0])
  }

  return (
    <div
      onDragOver={(e) => { e.preventDefault(); setDragActive(true) }}
      onDragLeave={() => setDragActive(false)}
      onDrop={(e) => {
        e.preventDefault()
        setDragActive(false)
        handleFiles(e.dataTransfer.files)
      }}
      onClick={() => inputRef.current?.click()}
      className={`rounded-3xl border-2 border-dashed cursor-pointer transition-all p-16 text-center
        ${dragActive ? 'border-signal-cyan bg-signal-cyan/5' : 'border-border hover:border-signal-cyan/50'}`}
    >
      <input
        ref={inputRef}
        type="file"
        accept=".csv,.tsv,.txt,.xlsx,.xls,.json"
        className="hidden"
        onChange={(e) => handleFiles(e.target.files)}
      />
      {uploading ? (
        <>
          <Loader2 className="mx-auto mb-4 animate-spin text-signal-cyan" size={36} />
          <p className="font-display font-medium">Cleaning and profiling your data…</p>
          <p className="text-sm text-muted mt-1">This takes a few seconds.</p>
        </>
      ) : (
        <>
          <UploadCloud className="mx-auto mb-4 text-signal-cyan" size={36} />
          <p className="font-display font-medium text-lg mb-1">Drop your file here, or click to browse</p>
          <p className="text-sm text-muted flex items-center justify-center gap-1.5">
            <FileSpreadsheet size={14} /> CSV · TSV · TXT · XLSX · XLS · JSON — up to 50MB
          </p>
        </>
      )}
    </div>
  )
}
