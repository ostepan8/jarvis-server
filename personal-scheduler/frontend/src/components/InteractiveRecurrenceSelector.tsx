import React, { useState } from 'react';
import { ChevronRight, Calendar, Clock, Repeat } from 'lucide-react';

export interface RecurrencePattern {
  type: 'daily' | 'weekly' | 'monthly' | 'yearly';
  interval: number;
  days?: number[]; // For weekly: 0=Sunday, 1=Monday, etc.
  max?: number; // -1 for unlimited
  end?: string; // ISO string
}

interface InteractiveRecurrenceSelectorProps {
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

const InteractiveRecurrenceSelector: React.FC<InteractiveRecurrenceSelectorProps> = ({
  value,
  onChange,
  startDate,
}) => {
  const [step, setStep] = useState<'type' | 'interval' | 'days' | 'end'>('type');

  const handleTypeSelect = (type: RecurrencePattern['type']) => {
    const newPattern: RecurrencePattern = {
      type,
      interval: 1,
      max: -1,
    };

    if (type === 'weekly') {
      newPattern.days = [startDate.getDay()];
      setStep('days');
    } else {
      setStep('interval');
    }

    onChange(newPattern);
  };

  const handleIntervalSet = () => {
    setStep('end');
  };

  const handleDaysSet = () => {
    setStep('interval');
  };

  const handleEndSet = () => {
    setStep('type'); // Reset for potential editing
  };

  const getSummary = () => {
    const { type, interval, days, max, end } = value;
    
    let summary = `Every ${interval > 1 ? interval + ' ' : ''}${
      type === 'daily' ? (interval === 1 ? 'day' : 'days') :
      type === 'weekly' ? (interval === 1 ? 'week' : 'weeks') :
      type === 'monthly' ? (interval === 1 ? 'month' : 'months') :
      (interval === 1 ? 'year' : 'years')
    }`;

    if (type === 'weekly' && days && days.length > 0) {
      const dayNames = days.map(d => WEEKDAYS.find(wd => wd.value === d)?.label).join(', ');
      summary += ` on ${dayNames}`;
    }

    if (max && max > 0) {
      summary += ` (${max}×)`;
    } else if (end) {
      const endDate = new Date(end);
      summary += ` until ${endDate.toLocaleDateString('en-US', { month: 'short', day: 'numeric' })}`;
    }

    return summary;
  };

  return (
    <div className="space-y-1.5">
      {/* Summary Badge */}
      <div className="flex items-center justify-between p-2 bg-primary-50 rounded-lg border text-sm">
        <div className="flex items-center space-x-2">
          <Repeat size={16} className="text-primary-600" />
          <span className="text-sm font-medium text-primary-800">
            {getSummary()}
          </span>
        </div>
        <button
          type="button"
          onClick={() => setStep('type')}
          className="text-sm text-primary-600 hover:text-primary-800 font-medium"
        >
          Edit
        </button>
      </div>

      {/* Interactive Steps */}
      {step === 'type' && (
        <div className="space-y-1.5">
          <h4 className="text-sm font-medium text-gray-700">How often should this repeat?</h4>
          <div className="grid grid-cols-2 gap-1">
            {(['daily', 'weekly', 'monthly', 'yearly'] as const).map((type) => (
              <button
                key={type}
                type="button"
                onClick={() => handleTypeSelect(type)}
                className={`p-2 text-left rounded-lg border transition-colors ${
                  value.type === type
                    ? 'border-primary-300 bg-primary-50 text-primary-800'
                    : 'border-gray-200 hover:border-gray-300 hover:bg-gray-50'
                }`}
              >
                <div className="font-medium capitalize">{type}</div>
                <div className="text-xs text-gray-600 mt-1">
                  {type === 'daily' && 'Every day or every few days'}
                  {type === 'weekly' && 'Specific days of the week'}
                  {type === 'monthly' && 'Same date each month'}
                  {type === 'yearly' && 'Annual events'}
                </div>
              </button>
            ))}
          </div>
        </div>
      )}

      {step === 'days' && value.type === 'weekly' && (
        <div className="space-y-1.5">
          <div className="flex items-center justify-between">
            <h4 className="text-sm font-medium text-gray-700">Which days?</h4>
            <button
              type="button"
              onClick={() => setStep('type')}
              className="text-sm text-gray-500 hover:text-gray-700"
            >
              ← Back
            </button>
          </div>
          <div className="grid grid-cols-7 gap-1">
            {WEEKDAYS.map(day => (
              <button
                key={day.value}
                type="button"
                onClick={() => {
                  const currentDays = value.days || [];
                  const newDays = currentDays.includes(day.value)
                    ? currentDays.filter(d => d !== day.value)
                    : [...currentDays, day.value].sort();
                  onChange({ ...value, days: newDays });
                }}
                className={`py-2 text-xs font-medium rounded transition-colors ${
                  value.days?.includes(day.value)
                    ? 'bg-primary-600 text-white'
                    : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
                }`}
              >
                {day.label}
              </button>
            ))}
          </div>
          <button
            type="button"
            onClick={handleDaysSet}
            disabled={!value.days || value.days.length === 0}
            className="w-full flex items-center justify-center space-x-1 py-1.5 text-sm bg-primary-600 text-white rounded-md hover:bg-primary-700 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            <span>Continue</span>
            <ChevronRight size={16} />
          </button>
        </div>
      )}

      {step === 'interval' && (
        <div className="space-y-2">
          <div className="flex items-center justify-between">
            <h4 className="text-sm font-medium text-gray-700">Every how many {value.type === 'daily' ? 'days' : value.type === 'weekly' ? 'weeks' : value.type === 'monthly' ? 'months' : 'years'}?</h4>
            <button
              type="button"
              onClick={() => setStep(value.type === 'weekly' ? 'days' : 'type')}
              className="text-sm text-gray-500 hover:text-gray-700"
            >
              ← Back
            </button>
          </div>
          <div className="flex items-center space-x-2">
            <input
              type="number"
              min="1"
              max="99"
              value={value.interval}
              onChange={(e) => onChange({ ...value, interval: Math.max(1, parseInt(e.target.value) || 1) })}
              className="w-16 px-2 py-1 text-center border border-gray-300 rounded focus:outline-none focus:ring-2 focus:ring-primary-500"
            />
            <span className="text-sm text-gray-600">
              {value.type === 'daily' ? (value.interval === 1 ? 'day' : 'days') :
               value.type === 'weekly' ? (value.interval === 1 ? 'week' : 'weeks') :
               value.type === 'monthly' ? (value.interval === 1 ? 'month' : 'months') :
               (value.interval === 1 ? 'year' : 'years')}
            </span>
          </div>
          <button
            type="button"
            onClick={handleIntervalSet}
            className="w-full flex items-center justify-center space-x-2 py-2 bg-primary-600 text-white rounded-md hover:bg-primary-700"
          >
            <span>Continue</span>
            <ChevronRight size={16} />
          </button>
        </div>
      )}

      {step === 'end' && (
        <div className="space-y-2">
          <div className="flex items-center justify-between">
            <h4 className="text-sm font-medium text-gray-700">When should it end?</h4>
            <button
              type="button"
              onClick={() => setStep('interval')}
              className="text-sm text-gray-500 hover:text-gray-700"
            >
              ← Back
            </button>
          </div>
          <div className="space-y-2">
            <label className="flex items-center cursor-pointer p-2 rounded hover:bg-gray-50">
              <input
                type="radio"
                name="endOption"
                checked={!value.max || value.max === -1}
                onChange={() => onChange({ ...value, max: -1, end: undefined })}
                className="mr-3"
              />
              <div>
                <div className="text-sm font-medium">Never</div>
                <div className="text-xs text-gray-500">Continues indefinitely</div>
              </div>
            </label>

            <label className="flex items-center cursor-pointer p-2 rounded hover:bg-gray-50">
              <input
                type="radio"
                name="endOption"
                checked={!!(value.max && value.max > 0)}
                onChange={() => onChange({ ...value, max: 10, end: undefined })}
                className="mr-3"
              />
              <div className="flex items-center space-x-2">
                <div>
                  <div className="text-sm font-medium">After</div>
                  <div className="text-xs text-gray-500">Specific number of times</div>
                </div>
                {value.max && value.max > 0 && (
                  <input
                    type="number"
                    min="1"
                    max="999"
                    value={value.max}
                    onChange={(e) => onChange({ ...value, max: Math.max(1, parseInt(e.target.value) || 10) })}
                    className="w-16 px-2 py-1 text-sm text-center border border-gray-300 rounded focus:outline-none focus:ring-1 focus:ring-primary-500"
                    onClick={(e) => e.stopPropagation()}
                  />
                )}
              </div>
            </label>

            <label className="flex items-center cursor-pointer p-2 rounded hover:bg-gray-50">
              <input
                type="radio"
                name="endOption"
                checked={!!value.end}
                onChange={() => {
                  const defaultEndDate = new Date(startDate);
                  defaultEndDate.setMonth(defaultEndDate.getMonth() + 1);
                  onChange({ ...value, max: -1, end: defaultEndDate.toISOString().split('T')[0] });
                }}
                className="mr-3"
              />
              <div className="flex items-center space-x-2">
                <div>
                  <div className="text-sm font-medium">On date</div>
                  <div className="text-xs text-gray-500">Specific end date</div>
                </div>
                {value.end && (
                  <input
                    type="date"
                    value={value.end.split('T')[0]}
                    onChange={(e) => onChange({ ...value, end: e.target.value })}
                    className="px-2 py-1 text-sm border border-gray-300 rounded focus:outline-none focus:ring-1 focus:ring-primary-500"
                    onClick={(e) => e.stopPropagation()}
                  />
                )}
              </div>
            </label>
          </div>
          <button
            type="button"
            onClick={handleEndSet}
            className="w-full py-2 bg-green-600 text-white rounded-md hover:bg-green-700 font-medium"
          >
            Done ✓
          </button>
        </div>
      )}
    </div>
  );
};

export default InteractiveRecurrenceSelector;