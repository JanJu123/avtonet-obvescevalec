## Bot Not Sending Ads - Root Cause Analysis & Fix

### The Problem
User reported: "Bot is running, scanning URLs successfully, finding [REUSE] ads in cache, but sending 0 ads to users"

### Root Cause
The bot had a **fundamental flaw in the first-scan logic**:

1. **First Scan (when URL first added):**
   - Bot finds ALL ads on the website
   - Marks them all as "sent" in SentAds table via `bulk_add_sent_ads()`
   - Returns immediately WITHOUT adding them to ScrapedData table
   - **Result: User receives 0 ads on first connect**

2. **Subsequent Scans (120 seconds later):**
   - Same ads reappear on website
   - Bot checks: "Is this ad new?" via `is_ad_new()` which checks SentAds
   - All ads are already in SentAds from first scan
   - `is_ad_new()` returns FALSE for all
   - Ads don't go to AI batch
   - Ads don't get added to ScrapedData
   - `check_new_offers()` finds nothing to send
   - **Result: User continues receiving 0 ads**

3. **Only if NEW ads appear on website:**
   - They wouldn't be in SentAds yet
   - They would be processed and added to ScrapedData
   - They would be sent to user

**In summary:** The system was designed to only send ads that are genuinely NEW to the website. But because the first-scan initialization was broken, users never received their initial batch of ads.

### Database State Verification
Checked local VPS replica database:
- **SentAds:** 3441 records (all marked "sent")
- **MarketData:** 909 records (cached ads)
- **ScrapedData:** 3 records total (almost empty!)
- **Available to send:** 0 ads

### The Fix
Changed scraper.py logic to **treat first scan like any other scan**:

**Before:**
```python
if not is_first and self.db.is_ad_new(content_id):
    # Only process ads on 2nd+ scans, not on first scan
```

**After:**
```python
if is_first or self.db.is_ad_new(content_id):
    # Process ads on ANY scan (first or subsequent)
```

### Detailed Changes
1. **Removed the `is_first` check** that was skipping ad processing on first scan
2. **Updated first-scan ad handling:**
   - [REUSE] ads (already in MarketData) are now added to `final_results` on first scan only
   - New ads are processed normally by AI
3. **Removed the early `continue` statement** that was preventing ScrapedData insertion on first scan
4. **Let the normal ad insertion flow handle everything:**
   - All ads added to ScrapedData
   - Check_new_offers() finds ads not yet sent
   - Ads sent to user
   - Ads marked as "sent" in SentAds

### Flow After Fix

**First Scan:**
```
Website ads found → Process all → Add to ScrapedData → check_new_offers() finds them → 
Send to user → Mark as sent in SentAds
```

**Second+ Scan (same ads):**
```
Website ads found → Check is_ad_new() → Already in SentAds → Skip → 
Nothing added to ScrapedData → Nothing to send (correct!)
```

**When NEW ads appear:**
```
NEW website ad → Not in SentAds → Process normally → Add to ScrapedData → 
check_new_offers() finds it → Send to user
```

### Testing on VPS
Next steps:
1. Pull the updated code: `git pull origin restart-from-stable`
2. Restart the bot
3. Monitor for:
   - Ads being added to ScrapedData on first/next scan
   - check_new_offers() returning results
   - Telegram notifications being sent to users
   - No duplicate sends (already in SentAds protection works)

### Expected Behavior
- **Users with existing URLs:** Should receive initial batch of ads on next scan
- **New URLs:** Should send ads immediately on first scan
- **Subsequent scans:** Only new/unseen ads will be sent (no duplicates)
- **[REUSE] message:** Only shown during scanning, not when sending to users
