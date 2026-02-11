import { useState } from 'react';
import { FileDown, FileSpreadsheet, Loader2 } from 'lucide-react';
import { EarningsAnalysis } from '../../types/earnings';
import { exportToPDF, exportToExcel } from '../../utils/earningsExport';

interface ExportActionsProps {
  data: EarningsAnalysis;
  dashboardElementId: string;
}

export default function ExportActions({ data, dashboardElementId }: ExportActionsProps) {
  const [isExportingPDF, setIsExportingPDF] = useState(false);
  const [isExportingExcel, setIsExportingExcel] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handlePDFExport = async () => {
    try {
      setIsExportingPDF(true);
      setError(null);
      await exportToPDF(dashboardElementId, data.ticker);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'PDF export failed');
    } finally {
      setIsExportingPDF(false);
    }
  };

  const handleExcelExport = () => {
    try {
      setIsExportingExcel(true);
      setError(null);
      exportToExcel(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Excel export failed');
    } finally {
      setIsExportingExcel(false);
    }
  };

  return (
    <div className="sticky bottom-0 z-20 glass-effect border-t border-slate-200/50 shadow-lg">
      <div className="max-w-7xl mx-auto px-6 py-4">
        <div className="flex flex-col md:flex-row items-center justify-between gap-4">
          {/* Export Info */}
          <div className="text-sm text-slate-600">
            <span className="font-medium">Export this analysis</span>
            <span className="ml-2 text-slate-500">Save for later review or share with your team</span>
          </div>

          {/* Export Buttons */}
          <div className="flex items-center gap-3">
            {/* PDF Export Button */}
            <button
              onClick={handlePDFExport}
              disabled={isExportingPDF || isExportingExcel}
              className="px-6 py-2.5 rounded-xl font-semibold
                text-white bg-gradient-to-r from-red-600 to-red-700
                hover:from-red-700 hover:to-red-800
                disabled:from-slate-300 disabled:to-slate-400 disabled:cursor-not-allowed
                shadow-lg shadow-red-500/30 hover:shadow-xl hover:shadow-red-500/40
                transform hover:scale-105 active:scale-95
                transition-all duration-200
                flex items-center gap-2"
            >
              {isExportingPDF ? (
                <>
                  <Loader2 className="h-5 w-5 animate-spin" />
                  <span>Generating PDF...</span>
                </>
              ) : (
                <>
                  <FileDown className="h-5 w-5" />
                  <span>Export PDF</span>
                </>
              )}
            </button>

            {/* Excel Export Button */}
            <button
              onClick={handleExcelExport}
              disabled={isExportingPDF || isExportingExcel}
              className="px-6 py-2.5 rounded-xl font-semibold
                text-white bg-gradient-to-r from-green-600 to-green-700
                hover:from-green-700 hover:to-green-800
                disabled:from-slate-300 disabled:to-slate-400 disabled:cursor-not-allowed
                shadow-lg shadow-green-500/30 hover:shadow-xl hover:shadow-green-500/40
                transform hover:scale-105 active:scale-95
                transition-all duration-200
                flex items-center gap-2"
            >
              {isExportingExcel ? (
                <>
                  <Loader2 className="h-5 w-5 animate-spin" />
                  <span>Generating Excel...</span>
                </>
              ) : (
                <>
                  <FileSpreadsheet className="h-5 w-5" />
                  <span>Export Excel</span>
                </>
              )}
            </button>
          </div>
        </div>

        {/* Error Message */}
        {error && (
          <div className="mt-3 p-3 bg-red-50 border border-red-200 rounded-lg text-sm text-red-700">
            <span className="font-semibold">Export Error:</span> {error}
          </div>
        )}

        {/* Export Info Text */}
        <div className="mt-3 text-xs text-slate-500 text-center md:text-right">
          PDF captures the full visual dashboard • Excel provides structured data tables
        </div>
      </div>
    </div>
  );
}
