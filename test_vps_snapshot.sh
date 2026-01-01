#!/bin/bash
# Run this on VPS BEFORE and AFTER bot scans

echo "=========================================="
echo "Database snapshot at: $(date)"
echo "=========================================="

sqlite3 bot.db <<EOF
-- 1. Count ads in each table
SELECT 'ScrapedData count:' as info, COUNT(*) as count FROM ScrapedData;
SELECT 'MarketData count:' as info, COUNT(*) as count FROM MarketData;
SELECT 'SentAds count:' as info, COUNT(*) as count FROM SentAds;

-- 2. Recent ads in ScrapedData (top 10 by content_id)
.print ""
.print "Recent ScrapedData ads:"
SELECT content_id, url_id FROM ScrapedData ORDER BY content_id DESC LIMIT 10;

-- 3. Recent ads in MarketData (top 10 by content_id)
.print ""
.print "Recent MarketData ads:"
SELECT content_id, enriched, created_at FROM MarketData ORDER BY content_id DESC LIMIT 10;

-- 4. Ads in ScrapedData but NOT in MarketData
.print ""
.print "Ads in ScrapedData but NOT in MarketData:"
SELECT sd.content_id, sd.url_id 
FROM ScrapedData sd 
WHERE NOT EXISTS (SELECT 1 FROM MarketData md WHERE md.content_id = sd.content_id)
LIMIT 20;

-- 5. Ads ready to send (in both ScrapedData and MarketData, not in SentAds)
.print ""
.print "Ads ready to send for user 8004323652:"
SELECT sd.content_id, sd.url_id
FROM ScrapedData sd
JOIN Tracking t ON sd.url_id = t.url_id
WHERE t.telegram_id = 8004323652
AND EXISTS (SELECT 1 FROM MarketData md WHERE md.content_id = sd.content_id)
AND NOT EXISTS (SELECT 1 FROM SentAds sa WHERE sa.content_id = sd.content_id AND sa.telegram_id = 8004323652)
LIMIT 20;

-- 6. User tracking status
.print ""
.print "User 8004323652 tracking:"
SELECT url_id, last_notified_at FROM Tracking WHERE telegram_id = 8004323652;

-- 7. User scan_interval
.print ""
.print "User 8004323652 scan_interval:"
SELECT scan_interval, is_active FROM Users WHERE telegram_id = 8004323652;
EOF

echo ""
echo "=========================================="
