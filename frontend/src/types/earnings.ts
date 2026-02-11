// Earnings Dashboard Types

export interface MetricData {
  value: number;
  change: number;
  changePercent: number;
  vsEstimate?: number;
}

export interface QuarterlyDataPoint {
  quarter: string;
  date: string;
  value: number;
  yoyGrowth?: number;
}

export interface SurpriseData {
  quarter: string;
  date: string;
  actualEPS: number;
  estimatedEPS: number;
  surprise: number;
  surprisePercent: number;
  beat: boolean;
}

export interface ManagementQuote {
  speaker: string;
  role: string;
  quote: string;
  topic: string;
  sentiment?: 'positive' | 'neutral' | 'negative';
}

export interface GuidanceData {
  nextQuarter?: {
    revenue?: string;
    eps?: string;
  };
  fullYear?: {
    revenue?: string;
    eps?: string;
  };
  commentary: string;
}

export interface PriceTargetData {
  current: number;
  high: number;
  low: number;
  median: number;
  numAnalysts: number;
}

export interface RatingChange {
  date: string;
  firm: string;
  action: string;
  fromRating: string;
  toRating: string;
}

export interface RatingsData {
  buy: number;
  hold: number;
  sell: number;
  consensus: string;
}

export interface PeerMetric {
  ticker: string;
  companyName: string;
  revenue: number;
  eps: number;
  yoyGrowth: number;
  margin: number;
}

export interface EarningsAnalysis {
  ticker: string;
  companyName: string;

  summary: {
    quarter: string;
    reportDate: string;
    revenue: MetricData;
    eps: MetricData;
    sentiment: string;
    highlights: string[];
  };

  quarterly: {
    revenue: QuarterlyDataPoint[];
    eps: QuarterlyDataPoint[];
  };

  surprises: SurpriseData[];

  commentary: {
    quotes: ManagementQuote[];
    guidance: GuidanceData;
    sentiment: string;
  };

  analyst: {
    priceTargets: PriceTargetData;
    ratings: RatingsData;
    recentChanges: RatingChange[];
  };

  peer: {
    comparison: PeerMetric[];
  };

  thesis: {
    rating: 'Buy' | 'Hold' | 'Sell';
    priceTarget: number;
    bullCase: string[];
    bearCase: string[];
    catalysts: string[];
    risks: string[];
  };
}

export interface LoadingStep {
  section: 'summary' | 'quarterly' | 'commentary' | 'analyst' | 'peer' | 'thesis';
  status: 'pending' | 'loading' | 'complete' | 'error';
  progress?: number;
  message?: string;
}
