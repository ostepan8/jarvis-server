# Known Limitations

## What Jarvis Cannot Do

### Communication
- Cannot send emails, SMS, or Slack messages
- Cannot make phone calls
- Cannot post to social media

### File System
- Cannot browse or manage files on your computer (beyond temp file cleanup via DeviceMonitorAgent)
- Cannot open or edit documents
- Cannot take screenshots

### Media
- Cannot play music directly (can launch music apps on Roku)
- Cannot record audio or video
- Cannot process images or PDFs

### Smart Home (Beyond Current Integrations)
- No thermostat control
- No door lock control
- No security camera access
- No smart speaker integration (beyond being one)
- No garage door control

### External Services
- No email integration
- No banking or financial services
- No food delivery or shopping
- No ride-hailing
- No social media management

### Real-Time
- Cannot stream live data (stock tickers, sports scores)
- Cannot maintain persistent WebSocket connections to external services
- Weather data comes via web search, not a dedicated weather API

## What Might Not Work (Conditional)

These capabilities depend on configuration and external services:

| Capability | Requires |
|-----------|----------|
| Lighting | Phillips Hue bridge or Yeelight bulbs configured |
| TV Control | Roku device(s) on the network |
| Web Search | Google Search API credentials |
| Vector Memory | OpenAI API key (for embeddings) |
| Calendar | Calendar API server running |
| Canvas | Canvas LMS credentials |

## Planned but Not Yet Implemented

Check the TodoAgent or SelfImprovementAgent for items in the backlog.
