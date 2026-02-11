import jsPDF from 'jspdf';
import html2canvas from 'html2canvas';
import * as XLSX from 'xlsx';
import { EarningsAnalysis } from '../types/earnings';

/**
 * Export earnings analysis to PDF
 * Captures the rendered dashboard and converts to PDF
 */
export async function exportToPDF(
  elementId: string,
  ticker: string
): Promise<void> {
  try {
    const element = document.getElementById(elementId);
    if (!element) {
      throw new Error('Dashboard element not found');
    }

    // Show loading state
    const originalCursor = document.body.style.cursor;
    document.body.style.cursor = 'wait';

    // Capture the dashboard as canvas
    const canvas = await html2canvas(element, {
      scale: 2, // Higher quality
      useCORS: true,
      logging: false,
      backgroundColor: '#ffffff',
    });

    // Create PDF
    const pdf = new jsPDF({
      orientation: 'portrait',
      unit: 'mm',
      format: 'a4',
    });

    // Calculate dimensions to fit A4 page
    const imgWidth = 210; // A4 width in mm
    const pageHeight = 297; // A4 height in mm
    const imgHeight = (canvas.height * imgWidth) / canvas.width;
    let heightLeft = imgHeight;
    let position = 0;

    // Add first page
    const imgData = canvas.toDataURL('image/png');
    pdf.addImage(imgData, 'PNG', 0, position, imgWidth, imgHeight);
    heightLeft -= pageHeight;

    // Add additional pages if content is longer than one page
    while (heightLeft > 0) {
      position = heightLeft - imgHeight;
      pdf.addPage();
      pdf.addImage(imgData, 'PNG', 0, position, imgWidth, imgHeight);
      heightLeft -= pageHeight;
    }

    // Generate filename with timestamp
    const timestamp = new Date().toISOString().split('T')[0];
    const filename = `${ticker}_Earnings_Analysis_${timestamp}.pdf`;

    // Download
    pdf.save(filename);

    // Restore cursor
    document.body.style.cursor = originalCursor;
  } catch (error) {
    console.error('PDF export failed:', error);
    document.body.style.cursor = 'default';
    throw new Error('Failed to generate PDF. Please try again.');
  }
}

/**
 * Export earnings analysis to Excel
 * Creates multiple sheets with structured data
 */
export function exportToExcel(data: EarningsAnalysis): void {
  try {
    const workbook = XLSX.utils.book_new();

    // Sheet 1: Summary
    const summaryData = [
      ['Ticker', data.ticker],
      ['Company', data.companyName],
      ['Quarter', data.summary.quarter],
      ['Report Date', data.summary.reportDate],
      [''],
      ['Revenue', data.summary.revenue.value],
      ['Revenue Change', data.summary.revenue.change],
      ['Revenue Change %', data.summary.revenue.changePercent],
      [''],
      ['EPS', data.summary.eps.value],
      ['EPS Change', data.summary.eps.change],
      ['EPS Change %', data.summary.eps.changePercent],
      [''],
      ['Sentiment', data.summary.sentiment],
      [''],
      ['Highlights'],
      ...data.summary.highlights.map(h => [h]),
    ];
    const summarySheet = XLSX.utils.aoa_to_sheet(summaryData);
    XLSX.utils.book_append_sheet(workbook, summarySheet, 'Summary');

    // Sheet 2: Quarterly Data
    if (data.quarterly.revenue.length > 0) {
      const quarterlyData = [
        ['Quarter', 'Date', 'Revenue', 'Revenue YoY Growth %', 'EPS', 'EPS YoY Growth %'],
        ...data.quarterly.revenue.map((rev, idx) => [
          rev.quarter,
          rev.date,
          rev.value,
          rev.yoyGrowth || 0,
          data.quarterly.eps[idx]?.value || 0,
          data.quarterly.eps[idx]?.yoyGrowth || 0,
        ]),
      ];
      const quarterlySheet = XLSX.utils.aoa_to_sheet(quarterlyData);
      XLSX.utils.book_append_sheet(workbook, quarterlySheet, 'Quarterly Trends');
    }

    // Sheet 3: Earnings Surprises
    if (data.surprises.length > 0) {
      const surprisesData = [
        ['Quarter', 'Date', 'Actual EPS', 'Estimated EPS', 'Surprise', 'Surprise %', 'Beat?'],
        ...data.surprises.map(s => [
          s.quarter,
          s.date,
          s.actualEPS,
          s.estimatedEPS,
          s.surprise,
          s.surprisePercent,
          s.beat ? 'Yes' : 'No',
        ]),
      ];
      const surprisesSheet = XLSX.utils.aoa_to_sheet(surprisesData);
      XLSX.utils.book_append_sheet(workbook, surprisesSheet, 'Earnings Surprises');
    }

    // Sheet 4: Management Commentary
    if (data.commentary.quotes.length > 0) {
      const commentaryData = [
        ['Speaker', 'Role', 'Topic', 'Sentiment', 'Quote'],
        ...data.commentary.quotes.map(q => [
          q.speaker,
          q.role,
          q.topic,
          q.sentiment || 'N/A',
          q.quote,
        ]),
      ];
      const commentarySheet = XLSX.utils.aoa_to_sheet(commentaryData);
      XLSX.utils.book_append_sheet(workbook, commentarySheet, 'Management Commentary');
    }

    // Sheet 5: Analyst Outlook
    const analystData = [
      ['Price Targets'],
      ['Current', data.analyst.priceTargets.current],
      ['High', data.analyst.priceTargets.high],
      ['Low', data.analyst.priceTargets.low],
      ['Median', data.analyst.priceTargets.median],
      ['Number of Analysts', data.analyst.priceTargets.numAnalysts],
      [''],
      ['Ratings'],
      ['Buy', data.analyst.ratings.buy],
      ['Hold', data.analyst.ratings.hold],
      ['Sell', data.analyst.ratings.sell],
      ['Consensus', data.analyst.ratings.consensus],
    ];
    const analystSheet = XLSX.utils.aoa_to_sheet(analystData);
    XLSX.utils.book_append_sheet(workbook, analystSheet, 'Analyst Outlook');

    // Sheet 6: Peer Comparison
    if (data.peer.comparison.length > 0) {
      const peerData = [
        ['Ticker', 'Company', 'Revenue', 'EPS', 'YoY Growth %', 'Margin %'],
        ...data.peer.comparison.map(p => [
          p.ticker,
          p.companyName,
          p.revenue,
          p.eps,
          p.yoyGrowth,
          p.margin,
        ]),
      ];
      const peerSheet = XLSX.utils.aoa_to_sheet(peerData);
      XLSX.utils.book_append_sheet(workbook, peerSheet, 'Peer Comparison');
    }

    // Sheet 7: Investment Thesis
    const thesisData = [
      ['Rating', data.thesis.rating],
      ['Price Target', data.thesis.priceTarget],
      [''],
      ['Bull Case'],
      ...data.thesis.bullCase.map(b => [b]),
      [''],
      ['Bear Case'],
      ...data.thesis.bearCase.map(b => [b]),
      [''],
      ['Catalysts'],
      ...data.thesis.catalysts.map(c => [c]),
      [''],
      ['Risks'],
      ...data.thesis.risks.map(r => [r]),
    ];
    const thesisSheet = XLSX.utils.aoa_to_sheet(thesisData);
    XLSX.utils.book_append_sheet(workbook, thesisSheet, 'Investment Thesis');

    // Generate filename with timestamp
    const timestamp = new Date().toISOString().split('T')[0];
    const filename = `${data.ticker}_Earnings_Analysis_${timestamp}.xlsx`;

    // Download
    XLSX.writeFile(workbook, filename);
  } catch (error) {
    console.error('Excel export failed:', error);
    throw new Error('Failed to generate Excel file. Please try again.');
  }
}

/**
 * Format currency for display
 */
export function formatCurrency(value: number): string {
  if (value >= 1000000000) {
    return `$${(value / 1000000000).toFixed(2)}B`;
  } else if (value >= 1000000) {
    return `$${(value / 1000000).toFixed(2)}M`;
  } else {
    return `$${value.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
  }
}

/**
 * Format percentage for display
 */
export function formatPercentage(value: number): string {
  const sign = value >= 0 ? '+' : '';
  return `${sign}${value.toFixed(2)}%`;
}

/**
 * Format large numbers for display
 */
export function formatNumber(value: number): string {
  if (value >= 1000000000) {
    return `${(value / 1000000000).toFixed(2)}B`;
  } else if (value >= 1000000) {
    return `${(value / 1000000).toFixed(2)}M`;
  } else if (value >= 1000) {
    return `${(value / 1000).toFixed(2)}K`;
  } else {
    return value.toFixed(2);
  }
}
