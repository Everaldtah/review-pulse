# ReviewPulse

> Competitor review monitoring with sentiment analysis — track what customers say about your competitors across G2, Trustpilot, and Capterra.

## The Problem

Your competitors' customer reviews are a goldmine of intelligence. When a competitor's customers complain about a missing feature, that's your sales opportunity. When they rave about something you don't have, that's your product roadmap. But manually checking G2, Trustpilot, and Capterra every day is tedious and inconsistent.

**ReviewPulse automatically monitors competitor reviews, analyzes sentiment, and alerts you when keywords you care about appear.**

## Features

- **Multi-Platform Monitoring**: Track reviews on G2, Trustpilot, and Capterra simultaneously
- **Sentiment Analysis**: Every review scored from -1.0 (very negative) to +1.0 (very positive)
- **Keyword Alerts**: Get notified when reviews mention specific words (e.g., "pricing", "integration", "slow")
- **Scheduled Fetching**: Automatically checks for new reviews every N hours
- **Insights Dashboard**: Per-source breakdown of ratings, sentiment trends, positive/negative splits
- **Review History**: Full searchable database of all collected reviews
- **Digest History**: Track sentiment trends over time
- **REST API**: Full API with `/docs` interactive explorer

## Tech Stack

- **Backend**: Python 3.11+, FastAPI
- **Scraping**: requests (with fallback to realistic demo data)
- **Sentiment Analysis**: Custom lexicon-based NLP (no external ML deps)
- **Database**: SQLite
- **Scheduler**: APScheduler

## Installation

```bash
git clone https://github.com/Everaldtah/review-pulse
cd review-pulse
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

## Usage

### Start the server
```bash
python main.py
```

Visit `http://localhost:8000/docs` for the interactive API.

### Add a competitor to monitor
```bash
curl -X POST http://localhost:8000/products \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Competitor X",
    "slug": "competitor-x",
    "g2_slug": "competitor-x",
    "trustpilot_slug": "competitor-x.com",
    "capterra_slug": "12345/competitor-x",
    "alert_keywords": ["pricing", "integration", "slow", "API", "support"],
    "alert_email": "product@yourcompany.com"
  }'
```

### Trigger a review fetch
```bash
curl -X POST http://localhost:8000/products/competitor-x/fetch
```

### Get insights (sentiment breakdown)
```bash
curl http://localhost:8000/products/competitor-x/insights
```

### Get reviews filtered by sentiment
```bash
curl "http://localhost:8000/products/competitor-x/reviews?sentiment=negative&limit=20"
```

### List all products being monitored
```bash
curl http://localhost:8000/products
```

## How It Works

1. **Add a competitor** with their slugs on G2/Trustpilot/Capterra
2. **Set keywords** you want to be alerted about (e.g., "migration", "pricing", "alternative")
3. ReviewPulse fetches reviews from each platform every 24 hours
4. Each review is **scored for sentiment** using the built-in NLP analyzer
5. **Keyword matches** are flagged and can trigger email alerts
6. The **insights endpoint** shows aggregate stats and trends by source

## Sentiment Score Interpretation

| Score | Meaning |
|-------|---------|
| > 0.1 | Positive |
| -0.1 to 0.1 | Neutral |
| < -0.1 | Negative |

## Monetization Model

- **Free**: 2 competitors, 7-day review history
- **Starter — $39/month**: 10 competitors, all platforms, keyword alerts, 90-day history
- **Growth — $99/month**: 30 competitors, Slack/email digests, sentiment trend charts, API access
- **Agency — $299/month**: Unlimited competitors, white-label reports, team access, priority support

**Target users**: SaaS product managers, competitive intelligence analysts, sales teams, marketing teams.

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `DB_PATH` | SQLite database file | `review_pulse.db` |
| `CHECK_INTERVAL_HOURS` | Review fetch frequency | `24` |
| `SMTP_HOST` | SMTP host for alerts | `smtp.gmail.com` |
| `SMTP_PORT` | SMTP port | `587` |
| `SMTP_USER` | SMTP username | — |
| `SMTP_PASS` | SMTP password | — |

## License

MIT
