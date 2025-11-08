import React, { useState, useEffect } from 'react';
import { Repeat, Calendar, Clock } from 'lucide-react';

export interface RecurrencePattern {
  type: 'daily' | 'weekly' | 'monthly' | 'yearly';
  interval: number;
  days?: number[]; // For weekly: 0=Sunday, 1=Monday, etc.
  max?: number; // -1 for unlimited
  end?: string; // ISO string
}

interface RecurrencePatternSelectorProps {
  value: RecurrencePattern;
  onChange: (pattern: RecurrencePattern) => void;
  startDate: Date;
}

const WEEKDAYS = [
  { value: 0, label: 'Sun', name: 'Sunday' },
  { value: 1, label: 'Mon', name: 'Monday' },
  { value: 2, label: 'Tue', name: 'Tuesday' },
  { value: 3, label: 'Wed', name: 'Wednesday' },
  { value: 4, label: 'Thu', name: 'Thursday' },
  { value: 5, label: 'Fri', name: 'Friday' },
  { value: 6, label: 'Sat', name: 'Saturday' },
];

const RecurrencePatternSelector: React.FC<RecurrencePatternSelectorProps> = ({
  value,
  onChange,
  startDate,
}) => {
  const [endOption, setEndOption] = useState<'never' | 'on' | 'after'>('never');

  useEffect(() => {
    if (value.max && value.max > 0) {
      setEndOption('after');
    } else if (value.end) {
      setEndOption('on');
    } else {
      setEndOption('never');
    }
  }, [value.max, value.end]);

  const handleTypeChange = (type: RecurrencePattern['type']) => {
    const newPattern: RecurrencePattern = {
      type,
      interval: 1,
      max: -1,
    };

    // Set default days for weekly pattern
    if (type === 'weekly') {
      const startDay = startDate.getDay();
      newPattern.days = [startDay];
    }

    onChange(newPattern);
  };

  const handleIntervalChange = (interval: number) => {
    onChange({ ...value, interval: Math.max(1, interval) });
  };

  const handleDaysChange = (dayValue: number, checked: boolean) => {
    const currentDays = value.days || [];
    const newDays = checked
      ? [...currentDays, dayValue].sort()
      : currentDays.filter(d => d !== dayValue);
    
    onChange({ ...value, days: newDays });
  };

  const handleEndOptionChange = (option: 'never' | 'on' | 'after') => {
    setEndOption(option);
    
    if (option === 'never') {
      onChange({ 
        ...value, 
        max: -1, 
        end: undefined 
      });
    } else if (option === 'after') {
      onChange({ 
        ...value, 
        max: 10, 
        end: undefined 
      });
    } else if (option === 'on') {
      const defaultEndDate = new Date(startDate);
      defaultEndDate.setMonth(defaultEndDate.getMonth() + 1);
      onChange({ 
        ...value, 
        max: -1, 
        end: defaultEndDate.toISOString().split('T')[0] 
      });
    }
  };

  const handleMaxOccurrencesChange = (max: number) => {
    onChange({ ...value, max: Math.max(1, max) });
  };

  const handleEndDateChange = (endDate: string) => {
    onChange({ ...value, end: endDate });
  };

  const getIntervalLabel = () => {
    const { type, interval } = value;
    if (interval === 1) {
      return type === 'daily' ? 'day' : 
             type === 'weekly' ? 'week' :
             type === 'monthly' ? 'month' : 'year';
    } else {
      return type === 'daily' ? 'days' : 
             type === 'weekly' ? 'weeks' :
             type === 'monthly' ? 'months' : 'years';
    }
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center space-x-2 text-sm font-medium text-gray-700">
        <Repeat size={16} />
        <span>Repeat Pattern</span>
      </div>

      {/* Pattern Type */}
      <div>
        <label className="block text-sm font-medium text-gray-700 mb-2">
          Repeats
        </label>
        <select
          value={value.type}
          onChange={(e) => handleTypeChange(e.target.value as RecurrencePattern['type'])}
          className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-transparent"
        >
          <option value="daily">Daily</option>
          <option value="weekly">Weekly</option>
          <option value="monthly">Monthly</option>
          <option value="yearly">Yearly</option>
        </select>
      </div>

      {/* Interval */}
      <div>
        <label className="block text-sm font-medium text-gray-700 mb-2">
          Every
        </label>
        <div className="flex items-center space-x-2">
          <input
            type="number"
            min="1"
            max="999"
            value={value.interval}
            onChange={(e) => handleIntervalChange(parseInt(e.target.value))}
            className="w-20 px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-transparent"
          />
          <span className="text-sm text-gray-600">
            {getIntervalLabel()}
          </span>
        </div>
      </div>

      {/* Weekly Day Selection */}
      {value.type === 'weekly' && (
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-2">
            On these days
          </label>
          <div className="flex flex-wrap gap-2">
            {WEEKDAYS.map(day => (
              <label
                key={day.value}
                className="flex items-center cursor-pointer"
              >
                <input
                  type="checkbox"
                  checked={value.days?.includes(day.value) || false}
                  onChange={(e) => handleDaysChange(day.value, e.target.checked)}
                  className="sr-only"
                />
                <div className={`
                  w-10 h-8 flex items-center justify-center rounded text-xs font-medium transition-colors
                  ${value.days?.includes(day.value) 
                    ? 'bg-primary-600 text-white' 
                    : 'bg-gray-100 text-gray-700 hover:bg-gray-200'}
                `}>
                  {day.label}
                </div>
              </label>
            ))}
          </div>
        </div>
      )}

      {/* End Conditions */}
      <div>
        <label className="block text-sm font-medium text-gray-700 mb-2">
          Ends
        </label>
        <div className="space-y-3">
          <label className="flex items-center cursor-pointer">
            <input
              type="radio"
              name="endOption"
              value="never"
              checked={endOption === 'never'}
              onChange={() => handleEndOptionChange('never')}
              className="mr-2"
            />
            <span className="text-sm">Never</span>
          </label>

          <label className="flex items-center cursor-pointer">
            <input
              type="radio"
              name="endOption"
              value="on"
              checked={endOption === 'on'}
              onChange={() => handleEndOptionChange('on')}
              className="mr-2"
            />
            <span className="text-sm mr-2">On</span>
            <input
              type="date"
              disabled={endOption !== 'on'}
              value={value.end ? value.end.split('T')[0] : ''}
              onChange={(e) => handleEndDateChange(e.target.value)}
              className="px-2 py-1 text-sm border border-gray-300 rounded focus:outline-none focus:ring-1 focus:ring-primary-500 disabled:bg-gray-100"
            />
          </label>

          <label className="flex items-center cursor-pointer">
            <input
              type="radio"
              name="endOption"
              value="after"
              checked={endOption === 'after'}
              onChange={() => handleEndOptionChange('after')}
              className="mr-2"
            />
            <span className="text-sm mr-2">After</span>
            <input
              type="number"
              min="1"
              max="999"
              disabled={endOption !== 'after'}
              value={value.max && value.max > 0 ? value.max : 10}
              onChange={(e) => handleMaxOccurrencesChange(parseInt(e.target.value))}
              className="w-16 px-2 py-1 text-sm border border-gray-300 rounded focus:outline-none focus:ring-1 focus:ring-primary-500 disabled:bg-gray-100"
            />
            <span className="text-sm ml-1">occurrences</span>
          </label>
        </div>
      </div>

      {/* Summary */}
      <div className="bg-gray-50 p-3 rounded-md">
        <div className="text-xs text-gray-600">
          <strong>Summary:</strong> {getRecurrenceSummary(value, startDate)}
        </div>
      </div>
    </div>
  );
};

const getRecurrenceSummary = (pattern: RecurrencePattern, startDate: Date): string => {
  const { type, interval, days, max, end } = pattern;
  
  let summary = `Every ${interval > 1 ? interval + ' ' : ''}${
    type === 'daily' ? (interval === 1 ? 'day' : 'days') :
    type === 'weekly' ? (interval === 1 ? 'week' : 'weeks') :
    type === 'monthly' ? (interval === 1 ? 'month' : 'months') :
    (interval === 1 ? 'year' : 'years')
  }`;

  if (type === 'weekly' && days && days.length > 0) {
    const dayNames = days.map(d => WEEKDAYS.find(wd => wd.value === d)?.name).join(', ');
    summary += ` on ${dayNames}`;
  }

  if (max && max > 0) {
    summary += `, for ${max} occurrence${max === 1 ? '' : 's'}`;
  } else if (end) {
    const endDate = new Date(end);
    summary += `, until ${endDate.toLocaleDateString()}`;
  }

  return summary;
};

export default RecurrencePatternSelector;