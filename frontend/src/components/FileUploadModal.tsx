import { useCallback, useRef, useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Upload, X, FileText, FileSpreadsheet, File } from 'lucide-react';
import { UploadedFile } from '../types';

interface FileUploadModalProps {
  isOpen: boolean;
  onClose: () => void;
  attachedFiles: UploadedFile[];
  onFilesAdded: (files: File[]) => void;
  onFileRemove: (id: string) => void;
  isUploading: boolean;
}

const ACCEPTED_EXTENSIONS = ['.pdf', '.docx', '.pptx', '.xlsx', '.csv'];
const ACCEPTED_MIME_TYPES = [
  'application/pdf',
  'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
  'application/vnd.openxmlformats-officedocument.presentationml.presentation',
  'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
  'text/csv',
];
const MAX_FILE_SIZE = 10 * 1024 * 1024; // 10MB

function getFileIcon(name: string) {
  const ext = name.split('.').pop()?.toLowerCase();
  if (ext === 'xlsx' || ext === 'csv') return FileSpreadsheet;
  if (ext === 'pdf' || ext === 'docx') return FileText;
  return File;
}

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function FileUploadModal({
  isOpen,
  onClose,
  attachedFiles,
  onFilesAdded,
  onFileRemove,
  isUploading,
}: FileUploadModalProps) {
  const [dragOver, setDragOver] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const validateAndAdd = useCallback(
    (fileList: FileList | File[]) => {
      setError(null);
      const files = Array.from(fileList);
      const valid: File[] = [];

      for (const file of files) {
        const ext = '.' + file.name.split('.').pop()?.toLowerCase();
        if (!ACCEPTED_EXTENSIONS.includes(ext)) {
          setError(`Unsupported file type: ${ext}. Allowed: ${ACCEPTED_EXTENSIONS.join(', ')}`);
          continue;
        }
        if (file.size > MAX_FILE_SIZE) {
          setError(`${file.name} exceeds 10MB limit.`);
          continue;
        }
        valid.push(file);
      }

      if (valid.length > 0) {
        onFilesAdded(valid);
      }
    },
    [onFilesAdded]
  );

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      setDragOver(false);
      if (e.dataTransfer.files.length > 0) {
        validateAndAdd(e.dataTransfer.files);
      }
    },
    [validateAndAdd]
  );

  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(true);
  }, []);

  const handleDragLeave = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(false);
  }, []);

  const handleBrowse = () => {
    inputRef.current?.click();
  };

  const handleInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files.length > 0) {
      validateAndAdd(e.target.files);
      e.target.value = '';
    }
  };

  return (
    <AnimatePresence>
      {isOpen && (
        <motion.div
          className="file-upload-backdrop"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.15 }}
          onClick={onClose}
          onKeyDown={(e) => e.key === 'Escape' && onClose()}
        >
          <motion.div
            className="file-upload-modal"
            initial={{ opacity: 0, scale: 0.95, y: 8 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.95, y: 8 }}
            transition={{ duration: 0.15 }}
            onClick={(e) => e.stopPropagation()}
          >
            {/* Header */}
            <div className="file-upload-header">
              <span>Attach Documents</span>
              <button className="file-upload-close" onClick={onClose}>
                <X className="w-4 h-4" />
              </button>
            </div>

            {/* Drop zone */}
            <div
              className={`file-drop-zone ${dragOver ? 'drag-over' : ''}`}
              onDrop={handleDrop}
              onDragOver={handleDragOver}
              onDragLeave={handleDragLeave}
              onClick={handleBrowse}
            >
              <Upload className="w-6 h-6" style={{ color: dragOver ? '#10B981' : '#9CA3AF' }} />
              <p className="file-drop-text">
                Drag & drop files here, or <span className="file-drop-browse">browse</span>
              </p>
              <p className="file-drop-hint">
                PDF, DOCX, PPTX, XLSX, CSV &middot; Max 10MB
              </p>
            </div>

            <input
              ref={inputRef}
              type="file"
              multiple
              accept={ACCEPTED_MIME_TYPES.join(',')}
              style={{ display: 'none' }}
              onChange={handleInputChange}
            />

            {/* Error */}
            {error && (
              <div className="file-upload-error">{error}</div>
            )}

            {/* File list */}
            {attachedFiles.length > 0 && (
              <div className="file-list">
                {attachedFiles.map((f) => {
                  const Icon = getFileIcon(f.name);
                  return (
                    <div key={f.id} className="file-list-item">
                      <Icon className="w-4 h-4 flex-shrink-0" style={{ color: '#6B7280' }} />
                      <span className="file-list-name">{f.name}</span>
                      <span className="file-list-size">{formatSize(f.size)}</span>
                      {f.status === 'uploading' && (
                        <span className="file-list-status">Extracting...</span>
                      )}
                      {f.status === 'error' && (
                        <span className="file-list-status error">{f.error || 'Failed'}</span>
                      )}
                      <button
                        className="file-list-remove"
                        onClick={() => onFileRemove(f.id)}
                        title="Remove file"
                      >
                        <X className="w-3.5 h-3.5" />
                      </button>
                    </div>
                  );
                })}
              </div>
            )}

            {/* Done button */}
            <div className="file-upload-footer">
              <button
                className="file-upload-done"
                onClick={onClose}
                disabled={isUploading}
              >
                {isUploading ? 'Processing...' : 'Done'}
              </button>
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}

export default FileUploadModal;
