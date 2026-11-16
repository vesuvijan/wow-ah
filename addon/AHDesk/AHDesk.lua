-- AH Desk: collects character data into SavedVariables (written on /reload or logout)
-- and shows messages / alerts delivered through Inbox.lua (read on /reload or login).
-- No automation: it only reads game state and prints text.

local ADDON = "AHDesk"
local PREFIX = "|cffd8a83f[AH Desk]|r "
local SLOTS = { [1] = "HEAD", [2] = "NECK", [3] = "SHOULDER", [4] = "SHIRT", [5] = "CHEST", [6] = "WAIST", [7] = "LEGS", [8] = "FEET",
  [9] = "WRIST", [10] = "HANDS", [11] = "FINGER_1", [12] = "FINGER_2", [13] = "TRINKET_1", [14] = "TRINKET_2", [15] = "BACK",
  [16] = "MAIN_HAND", [17] = "OFF_HAND", [18] = "RANGED", [19] = "TABARD" }

local function safe(fn, ...)
  local ok, a, b, c, d = pcall(fn, ...)
  if ok then return a, b, c, d end
  return nil
end

local function now() return time() end

local function me()
  local name = UnitName("player") or "?"
  local realm = (GetNormalizedRealmName and GetNormalizedRealmName()) or (GetRealmName and GetRealmName()) or "?"
  return name .. "-" .. realm
end

local function moneyText(c)
  if not c then return "?" end
  c = math.floor(c + 0.5)
  local g, s, k = math.floor(c / 10000), math.floor(c / 100) % 100, c % 100
  if g > 0 then return g .. "g " .. s .. "s" end
  if s > 0 then return s .. "s " .. k .. "c" end
  return k .. "c"
end

-- ---------------------------------------------------------------- database
local function db()
  if type(AHDeskDB) ~= "table" then AHDeskDB = {} end
  local d = AHDeskDB
  d.v = 1
  d.chars = d.chars or {}
  d.outbox = d.outbox or {}
  d.seen = d.seen or {}
  d.ui = d.ui or {}
  return d
end

local function char()
  local d = db()
  local k = me()
  d.chars[k] = d.chars[k] or {}
  return d.chars[k]
end

-- ---------------------------------------------------------------- containers
local function numSlots(bag)
  if C_Container and C_Container.GetContainerNumSlots then return C_Container.GetContainerNumSlots(bag) or 0 end
  if GetContainerNumSlots then return GetContainerNumSlots(bag) or 0 end
  return 0
end

local function slotItem(bag, slot)
  if C_Container and C_Container.GetContainerItemInfo then
    local i = C_Container.GetContainerItemInfo(bag, slot)
    if i then return i.itemID, i.stackCount or 1, i.hyperlink end
    return nil
  end
  if GetContainerItemInfo then
    local _, count, _, _, _, _, link, _, _, id = GetContainerItemInfo(bag, slot)
    if link and not id then id = tonumber(link:match("item:(%d+)")) end
    return id, count or 1, link
  end
end

-- returns { { id=, c=, n=, l= }, ... } aggregated per distinct link (random suffixes stay apart)
local function scan(bags)
  local byKey, out, slots, used = {}, {}, 0, 0
  for _, bag in ipairs(bags) do
    local n = numSlots(bag)
    slots = slots + n
    for slot = 1, n do
      local id, count, link = slotItem(bag, slot)
      if id then
        used = used + 1
        local key = link and link:match("item:([%-%d:]+)") or tostring(id)
        local e = byKey[key]
        if not e then
          e = { id = id, c = 0, n = link and link:match("%[(.-)%]") or nil, k = key }
          byKey[key] = e
          out[#out + 1] = e
        end
        e.c = e.c + (count or 1)
      end
    end
  end
  return out, slots, used
end

local function scanBags()
  local c = char()
  c.bags, c.bagSlots, c.bagUsed = scan({ 0, 1, 2, 3, 4 })
  c.bagsAt = now()
end

local bankOpen = false
local function scanBank()
  if not bankOpen then return end
  local bags = { -1 }
  local n = NUM_BANKBAGSLOTS or 6
  for i = 1, n do bags[#bags + 1] = 4 + i end
  local c = char()
  c.bank, c.bankSlots, c.bankUsed = scan(bags)
  c.bankAt = now()
end

-- ---------------------------------------------------------------- character
local function scanGear()
  local c, gear = char(), {}
  for slot, name in pairs(SLOTS) do
    local link = GetInventoryItemLink("player", slot)
    if link then
      gear[name] = { id = GetInventoryItemID and GetInventoryItemID("player", slot) or tonumber(link:match("item:(%d+)")),
        n = link:match("%[(.-)%]"), k = link:match("item:([%-%d:]+)") }
    end
  end
  c.gear = gear
end

local function scanStats()
  local c, s = char(), {}
  local names = { "str", "agi", "sta", "int", "spi" }
  for i = 1, 5 do
    local base, stat = UnitStat("player", i)
    s[names[i]] = stat or base
  end
  s.hp = UnitHealthMax("player")
  s.mana = UnitPowerMax and UnitPowerMax("player", 0) or nil
  local b, p, n = UnitAttackPower("player")
  s.ap = (b or 0) + (p or 0) + (n or 0)
  if UnitRangedAttackPower then
    b, p, n = UnitRangedAttackPower("player")
    s.rap = (b or 0) + (p or 0) + (n or 0)
  end
  s.crit = GetCritChance and safe(GetCritChance) or nil
  s.rcrit = GetRangedCritChance and safe(GetRangedCritChance) or nil
  s.hit = GetHitModifier and safe(GetHitModifier) or nil
  s.dodge = GetDodgeChance and safe(GetDodgeChance) or nil
  local _, armor = UnitArmor("player")
  s.armor = armor
  if UnitRangedDamage then
    local speed, lo, hi = UnitRangedDamage("player")
    s.rspeed, s.rmin, s.rmax = speed, lo, hi
  end
  if UnitDamage then
    local lo, hi, olo, ohi = UnitDamage("player")
    s.mmin, s.mmax, s.omin, s.omax = lo, hi, olo, ohi
  end
  if UnitAttackSpeed then s.mspeed, s.ospeed = UnitAttackSpeed("player") end
  c.stats = s
  c.level = UnitLevel("player")
  c.class = select(2, UnitClass("player"))
  c.race = select(2, UnitRace("player"))
  c.faction = UnitFactionGroup("player")
  c.money = GetMoney()
  c.xp, c.xpMax = UnitXP("player"), UnitXPMax("player")
  c.rested = GetXPExhaustion and GetXPExhaustion() or nil
  c.zone = GetRealZoneText and GetRealZoneText() or nil
  c.subzone = GetSubZoneText and GetSubZoneText() or nil
  if UnitExists("pet") then
    c.pet = { n = UnitName("pet"), lvl = UnitLevel("pet"), fam = UnitCreatureFamily and UnitCreatureFamily("pet") or nil }
  end
end

local function scanProfessions()
  local c, out = char(), {}
  if GetProfessions and GetProfessionInfo then
    for _, idx in pairs({ GetProfessions() }) do
      if idx then
        local name, _, rank, maxRank, _, _, skillLine = GetProfessionInfo(idx)
        if name then out[#out + 1] = { n = name, r = rank, m = maxRank, id = skillLine } end
      end
    end
  end
  if #out == 0 and C_TradeSkillUI and C_TradeSkillUI.GetAllProfessionTradeSkillLines then
    for _, id in ipairs(C_TradeSkillUI.GetAllProfessionTradeSkillLines() or {}) do
      local i = C_TradeSkillUI.GetProfessionInfoBySkillLineID and C_TradeSkillUI.GetProfessionInfoBySkillLineID(id)
      if i and i.professionName then out[#out + 1] = { n = i.professionName, r = i.skillLevel, m = i.maxSkillLevel, id = id } end
    end
  end
  c.professions = out
end

local function scanSpecs()
  local c = char()
  local out = {}
  if C_SpecializationInfo and C_SpecializationInfo.GetSpecialization then
    out.active = C_SpecializationInfo.GetSpecialization()
    if GetSpecializationInfo and out.active then out.activeName = select(2, GetSpecializationInfo(out.active)) end
  end
  if C_ClassTalents and C_Traits and C_ClassTalents.GetActiveConfigID then
    local cfg = C_ClassTalents.GetActiveConfigID()
    if cfg then
      local info = C_Traits.GetConfigInfo(cfg)
      local picked = {}
      for _, tree in ipairs(info and info.treeIDs or {}) do
        for _, node in ipairs(C_Traits.GetTreeNodes(tree) or {}) do
          local ni = C_Traits.GetNodeInfo(cfg, node)
          if ni and ni.ranksPurchased and ni.ranksPurchased > 0 and ni.activeEntry then
            local e = C_Traits.GetEntryInfo(cfg, ni.activeEntry.entryID)
            local d = e and e.definitionID and C_Traits.GetDefinitionInfo(e.definitionID)
            local name = d and d.overrideName
            if not name and d and d.spellID and C_Spell and C_Spell.GetSpellName then name = C_Spell.GetSpellName(d.spellID) end
            picked[#picked + 1] = { n = name or tostring(node), r = ni.ranksPurchased, m = ni.maxRanks }
          end
        end
      end
      out.talents = picked
    end
  end
  c.specs = out
end

local function scanSkills()
  safe(scanProfessions); safe(scanSpecs)
  if not GetNumSkillLines then return end
  local c, out, header = char(), {}, nil
  for i = 1, GetNumSkillLines() do
    local name, isHeader, _, rank, _, mod, max = GetSkillLineInfo(i)
    if isHeader then header = name
    elseif name then out[#out + 1] = { n = name, r = rank, m = max, mod = mod, h = header } end
  end
  c.skills = out
end

local function scanReps()
  local c, out = char(), {}
  if GetNumFactions and GetFactionInfo then
    for i = 1, GetNumFactions() do
      local name, _, standing, lo, hi, val, _, _, isHeader = GetFactionInfo(i)
      if name and not isHeader then out[#out + 1] = { n = name, s = standing, v = val, lo = lo, hi = hi } end
    end
  elseif C_Reputation and C_Reputation.GetNumFactions and C_Reputation.GetFactionDataByIndex then
    for i = 1, C_Reputation.GetNumFactions() do
      local f = C_Reputation.GetFactionDataByIndex(i)
      if f and not f.isHeader then
        out[#out + 1] = { n = f.name, s = f.reaction, v = f.currentStanding, lo = f.currentReactionThreshold, hi = f.nextReactionThreshold }
      end
    end
  end
  c.reps = out
end

local function scanQuests()
  local c, out = char(), {}
  if C_QuestLog and C_QuestLog.GetInfo and C_QuestLog.GetNumQuestLogEntries then
    for i = 1, C_QuestLog.GetNumQuestLogEntries() do
      local q = C_QuestLog.GetInfo(i)
      if q and not q.isHeader then
        out[#out + 1] = { id = q.questID, n = q.title, lvl = q.level, done = C_QuestLog.IsComplete and C_QuestLog.IsComplete(q.questID) or nil }
      end
    end
  elseif GetNumQuestLogEntries and GetQuestLogTitle then
    for i = 1, GetNumQuestLogEntries() do
      local title, level, _, isHeader, _, isComplete, _, questID = GetQuestLogTitle(i)
      if title and not isHeader then out[#out + 1] = { id = questID, n = title, lvl = level, done = isComplete } end
    end
  end
  c.quests = out
end

local function scanTalents()
  if not (GetNumTalentTabs and GetNumTalents and GetTalentInfo) then return end
  local c, out = char(), {}
  for t = 1, GetNumTalentTabs() do
    local tab = { GetTalentTabInfo(t) }
    local tabName
    for _, v in ipairs(tab) do if type(v) == "string" and not tabName and not v:find("[\\/]") then tabName = v end end
    local e = { n = tabName, pts = 0, t = {} }
    for i = 1, GetNumTalents(t) do
      local name, _, _, _, rank, maxRank = GetTalentInfo(t, i)
      if name and rank and rank > 0 then
        e.t[#e.t + 1] = { n = name, r = rank, m = maxRank }
        e.pts = e.pts + rank
      end
    end
    out[#out + 1] = e
  end
  c.talents = out
end

local function scanAuctions()
  if not (GetNumAuctionItems and GetAuctionItemInfo) then return end
  local c, out = char(), {}
  local n = GetNumAuctionItems("owner") or 0
  for i = 1, n do
    local name, _, count, _, _, _, _, minBid, _, buyout, bid, _, _, _, _, sold, itemId = GetAuctionItemInfo("owner", i)
    if name then
      out[#out + 1] = { id = itemId, n = name, c = count, bo = buyout, bid = bid, min = minBid, sold = sold,
        left = GetAuctionItemTimeLeft and GetAuctionItemTimeLeft("owner", i) or nil }
    end
  end
  c.auctions = out
  c.auctionsAt = now()
end

local function scanMail()
  if not (GetInboxNumItems and GetInboxHeaderInfo) then return end
  local c, out = char(), {}
  for i = 1, GetInboxNumItems() do
    local _, _, sender, subject, money, cod, days, hasItem = GetInboxHeaderInfo(i)
    out[#out + 1] = { from = sender, s = subject, money = money, cod = cod, days = days, item = hasItem }
  end
  c.mail = out
  c.mailAt = now()
end

local function snapshot()
  safe(scanBags); safe(scanGear); safe(scanStats); safe(scanSkills)
  safe(scanReps); safe(scanQuests); safe(scanTalents); safe(scanBank)
  local c = char()
  c.at = now()
  db().last = me()
  db().lastAt = now()
end

-- ---------------------------------------------------------------- messages
local function inbox()
  if type(AHDeskInbox) ~= "table" then return {} end
  return AHDeskInbox.messages or {}
end

local ui = {}

local function stamp(t)
  if not t then return "" end
  return date("%d.%m %H:%M", t)
end

local function allMessages()
  local list = {}
  for _, m in ipairs(inbox()) do list[#list + 1] = { t = m.t or 0, who = (m.k == "alert") and "alert" or "claude", text = m.text or "" } end
  for _, m in ipairs(db().outbox) do list[#list + 1] = { t = m.t or 0, who = "me", text = m.text or "" } end
  table.sort(list, function(a, b) return a.t < b.t end)
  return list
end

local COLORS = { alert = "|cffe0a23a", claude = "|cff6aaef0", me = "|cff9aa0a8" }
local LABEL = { alert = "Alert", claude = "Claude", me = "You" }

local function refresh()
  if not ui.log then return end
  ui.log:Clear()
  for _, m in ipairs(allMessages()) do
    ui.log:AddMessage(string.format("|cff5b616c%s|r %s%s:|r %s", stamp(m.t), COLORS[m.who], LABEL[m.who], m.text))
  end
  if ui.info then
    local built = AHDeskInbox and AHDeskInbox.built
    ui.info:SetText("Inbox: " .. (built and stamp(built) or "none") .. "   |   /reload sends your data and messages")
  end
end

local function send(text)
  text = text and text:gsub("^%s+", ""):gsub("%s+$", "") or ""
  if text == "" then return end
  local d = db()
  d.outbox[#d.outbox + 1] = { t = now(), from = me(), text = text }
  while #d.outbox > 200 do table.remove(d.outbox, 1) end
  refresh()
end


-- ---------------------------------------------------------------- chat tab
local TAB = "AH Desk"
local function findTab()
  for i = 1, (NUM_CHAT_WINDOWS or 10) do
    local name = GetChatWindowInfo and GetChatWindowInfo(i)
    if name == TAB then return _G["ChatFrame" .. i] end
  end
end

local function ensureDocked(cf)
  if not cf then return end
  if FCF_DockFrame and GENERAL_CHAT_DOCK and FCFDock_GetChatFrames and not cf.isDocked then
    safe(FCF_DockFrame, cf, #FCFDock_GetChatFrames(GENERAL_CHAT_DOCK) + 1, false)
  end
  if FCF_SetWindowName then safe(FCF_SetWindowName, cf, TAB) end
end

local function buildTab()
  if ui.chat then return ui.chat end
  local cf = findTab()
  if not cf and FCF_OpenNewWindow then
    cf = FCF_OpenNewWindow(TAB)
  end
  if not cf then return end
  if ChatFrame_RemoveAllMessageGroups then ChatFrame_RemoveAllMessageGroups(cf) end
  if ChatFrame_RemoveAllChannels then ChatFrame_RemoveAllChannels(cf) end
  ui.chat = cf
  ensureDocked(cf)
  return cf
end

local function say(text, who)
  local cf = ui.chat or buildTab()
  local line = string.format("|cff5b616c%s|r %s%s:|r %s", stamp(now()), COLORS[who or "alert"], LABEL[who or "alert"], text)
  if cf then cf:AddMessage(line) else DEFAULT_CHAT_FRAME:AddMessage(PREFIX .. (who == "alert" and "|cffe0a23a" or "|cff6aaef0") .. text .. "|r") end
end


local function announceNew()
  local d, fresh, list = db(), 0, {}
  for _, m in ipairs(inbox()) do
    if m.id and not d.seen[m.id] then
      d.seen[m.id] = now()
      fresh = fresh + 1
      list[#list + 1] = m
    end
  end
  table.sort(list, function(x, y) return (x.t or 0) < (y.t or 0) end)
  local first = math.max(1, #list - 5)   -- show only the newest 6 in chat; the rest stays in the AH window
  for i = first, #list do
    local m = list[i]
    say(m.text or "", m.k == "alert" and "alert" or "claude")
  end
  if first > 1 then say((first - 1) .. " older messages: open the AH button window", "claude") end
  if fresh > 0 then
    DEFAULT_CHAT_FRAME:AddMessage(PREFIX .. "|cffffd100" .. fresh .. " new message" .. (fresh > 1 and "s" or "") ..
      " - check the AH Desk tab (or click the AH button)|r")
  end
  if fresh > 0 and PlaySound then safe(PlaySound, 3081) end
  if ui.badge then ui.badge:SetText(fresh > 0 and tostring(fresh) or "") end
end

-- ---------------------------------------------------------------- window
local function backdrop(f, alpha)
  if f.SetBackdrop then
    f:SetBackdrop({ bgFile = "Interface\\Buttons\\WHITE8x8", edgeFile = "Interface\\Buttons\\WHITE8x8", edgeSize = 1 })
    f:SetBackdropColor(0.08, 0.09, 0.10, alpha or 0.94)
    f:SetBackdropBorderColor(0.16, 0.17, 0.20, 1)
  end
end

local function buildWindow()
  if ui.frame then return end
  local tpl = BackdropTemplateMixin and "BackdropTemplate" or nil
  local f = CreateFrame("Frame", "AHDeskFrame", UIParent, tpl)
  f:SetSize(460, 330)
  f:SetPoint("CENTER")
  f:SetFrameStrata("HIGH")
  f:SetMovable(true); f:EnableMouse(true); f:SetClampedToScreen(true)
  f:RegisterForDrag("LeftButton")
  f:SetScript("OnDragStart", f.StartMoving)
  f:SetScript("OnDragStop", f.StopMovingOrSizing)
  backdrop(f)
  f:Hide()
  tinsert(UISpecialFrames, "AHDeskFrame")

  local title = f:CreateFontString(nil, "OVERLAY", "GameFontNormal")
  title:SetPoint("TOPLEFT", 12, -10)
  title:SetText("|cffd8a83fAH Desk|r")

  local close = CreateFrame("Button", nil, f, "UIPanelCloseButton")
  close:SetPoint("TOPRIGHT", 2, 2)

  local sync = CreateFrame("Button", nil, f, "UIPanelButtonTemplate")
  sync:SetSize(110, 20)
  sync:SetPoint("TOPRIGHT", -30, -7)
  sync:SetText("Sync (reload)")
  sync:SetScript("OnClick", function() snapshot(); ReloadUI() end)

  local log = CreateFrame("ScrollingMessageFrame", nil, f)
  log:SetPoint("TOPLEFT", 12, -34)
  log:SetPoint("BOTTOMRIGHT", -12, 56)
  log:SetFontObject(ChatFontNormal)
  log:SetJustifyH("LEFT")
  log:SetFading(false)
  log:SetMaxLines(400)
  log:EnableMouseWheel(true)
  log:SetScript("OnMouseWheel", function(self, delta)
    if delta > 0 then self:ScrollUp() else self:ScrollDown() end
  end)
  if log.SetHyperlinksEnabled then log:SetHyperlinksEnabled(true) end

  local edit = CreateFrame("EditBox", "AHDeskEdit", f, "InputBoxTemplate")
  edit:SetPoint("BOTTOMLEFT", 16, 28)
  edit:SetPoint("BOTTOMRIGHT", -12, 28)
  edit:SetHeight(20)
  edit:SetAutoFocus(false)
  edit:SetMaxLetters(400)
  edit:SetScript("OnEnterPressed", function(self) send(self:GetText()); self:SetText("") end)
  edit:SetScript("OnEscapePressed", function(self) self:ClearFocus() end)

  local info = f:CreateFontString(nil, "OVERLAY", "GameFontDisableSmall")
  info:SetPoint("BOTTOMLEFT", 12, 9)

  ui.frame, ui.log, ui.edit, ui.info = f, log, edit, info
end

local function toggle()
  buildWindow()
  if ui.frame:IsShown() then ui.frame:Hide() else refresh(); ui.frame:Show() end
end

local function buildButton()
  if ui.button then return end
  local tpl = BackdropTemplateMixin and "BackdropTemplate" or nil
  local b = CreateFrame("Button", "AHDeskButton", UIParent, tpl)
  b:SetSize(34, 20)
  local pos = db().ui.button
  if pos then b:SetPoint(pos[1], UIParent, pos[2], pos[3], pos[4]) else b:SetPoint("TOPRIGHT", UIParent, "TOPRIGHT", -220, -4) end
  b:SetMovable(true); b:SetClampedToScreen(true)
  b:RegisterForDrag("LeftButton")
  b:SetScript("OnDragStart", b.StartMoving)
  b:SetScript("OnDragStop", function(self)
    self:StopMovingOrSizing()
    local p, _, rp, x, y = self:GetPoint()
    db().ui.button = { p, rp, x, y }
  end)
  backdrop(b, 0.8)
  local t = b:CreateFontString(nil, "OVERLAY", "GameFontNormalSmall")
  t:SetPoint("LEFT", 6, 0)
  t:SetText("|cffd8a83fAH|r")
  local badge = b:CreateFontString(nil, "OVERLAY", "GameFontHighlightSmall")
  badge:SetPoint("RIGHT", -5, 0)
  b:SetScript("OnClick", function() badge:SetText(""); toggle() end)
  b:SetScript("OnEnter", function(self)
    GameTooltip:SetOwner(self, "ANCHOR_BOTTOMLEFT")
    GameTooltip:AddLine("AH Desk")
    GameTooltip:AddLine("Click: messages and alerts", 1, 1, 1)
    GameTooltip:AddLine("Drag to move. /ahd sync = save and reload", 0.6, 0.6, 0.6)
    GameTooltip:Show()
  end)
  b:SetScript("OnLeave", function() GameTooltip:Hide() end)
  ui.button, ui.badge = b, badge
end

-- ---------------------------------------------------------------- tooltip price line
local function onTooltipItem(tt)
  local prices = AHDeskInbox and AHDeskInbox.prices
  if not prices then return end
  local _, link = tt:GetItem()
  if not link then return end
  local id = tonumber(link:match("item:(%d+)"))
  local p = id and prices[id]
  if not p then return end
  local line = "AH " .. moneyText(p[1])
  if p[2] and p[2] > 0 then
    local pct = math.floor(100 * p[1] / p[2] - 100 + 0.5)
    line = line .. string.format("  (%s%d%% vs 7d)", pct > 0 and "+" or "", pct)
  end
  local r, g, b = 0.55, 0.58, 0.63
  if p[3] == "B" then line = line .. "  BUY"; r, g, b = 0.42, 0.68, 0.94
  elseif p[3] == "S" then line = line .. "  SELL"; r, g, b = 0.37, 0.77, 0.56 end
  tt:AddLine(line, r, g, b)
end

-- ---------------------------------------------------------------- events
local f = CreateFrame("Frame")

-- ---------------------------------------------------------------- upgrade check (live, no reload needed)
local WEIGHTS = {
  ITEM_MOD_AGILITY_SHORT = 1.0, ITEM_MOD_STAMINA_SHORT = 0.4, ITEM_MOD_INTELLECT_SHORT = 0.5,
  ITEM_MOD_ATTACK_POWER_SHORT = 0.5, ITEM_MOD_RANGED_ATTACK_POWER_SHORT = 0.5,
  ITEM_MOD_CRIT_RATING_SHORT = 1.0, ITEM_MOD_HIT_RATING_SHORT = 1.0, ITEM_MOD_STRENGTH_SHORT = 0.05,
  RESISTANCE0_NAME = 0.02,
}
local SLOT_OF = {
  INVTYPE_HEAD = { 1 }, INVTYPE_NECK = { 2 }, INVTYPE_SHOULDER = { 3 }, INVTYPE_CHEST = { 5 }, INVTYPE_ROBE = { 5 },
  INVTYPE_WAIST = { 6 }, INVTYPE_LEGS = { 7 }, INVTYPE_FEET = { 8 }, INVTYPE_WRIST = { 9 }, INVTYPE_HAND = { 10 },
  INVTYPE_FINGER = { 11, 12 }, INVTYPE_CLOAK = { 15 },
}
local function itemStats(link)
  local fn = (C_Item and C_Item.GetItemStats) or GetItemStats
  return link and fn and fn(link) or nil
end
local function score(link)
  local st, total = itemStats(link), 0
  if not st then return nil end
  for k, w in pairs(WEIGHTS) do total = total + (st[k] or 0) * w end
  return total
end
local function checkUpgrades()
  local d = db()
  d.upg = d.upg or {}
  local lvl = UnitLevel("player")
  for bag = 0, 4 do
    local slots = (C_Container and C_Container.GetContainerNumSlots or GetContainerNumSlots)(bag) or 0
    for slot = 1, slots do
      local link = (C_Container and C_Container.GetContainerItemLink or GetContainerItemLink)(bag, slot)
      if link then
        local id = tonumber(link:match("item:(%d+)"))
        if id and not d.upg[id] then
          local _, _, _, _, reqLevel, _, _, _, equipLoc, _, _, classID, subClass = GetItemInfo(link)
          local slotIds = equipLoc and SLOT_OF[equipLoc]
          local okType = classID == 4 and (subClass == 0 or subClass == 1 and equipLoc == "INVTYPE_CLOAK" or subClass == 2 or subClass == 3)
          if slotIds and okType and (reqLevel or 0) <= lvl then
            local new = score(link)
            if new then
              local worst, worstLink
              for _, sid in ipairs(slotIds) do
                local cur = GetInventoryItemLink("player", sid)
                local sc = cur and score(cur) or 0
                if not worst or sc < worst then worst, worstLink = sc, cur end
              end
              d.upg[id] = now()
              if worst and new - worst >= 1.5 then
                local name = GetItemInfo(link) or link
                local oldName = worstLink and (GetItemInfo(worstLink) or worstLink) or "empty slot"
                say("Upgrade: " .. name .. " is better than your " .. oldName .. " (+" .. string.format("%.1f", new - worst) ..
                  " score). Equip it.", "alert")
              end
            end
          end
        end
      end
    end
  end
end
local upgPending = false
local function queueUpgrades()
  if upgPending then return end
  upgPending = true
  C_Timer.After(3, function() upgPending = false; safe(checkUpgrades) end)
end

local events = { "ADDON_LOADED", "PLAYER_LOGIN", "PLAYER_LOGOUT", "BANKFRAME_OPENED", "BANKFRAME_CLOSED", "BAG_UPDATE_DELAYED",
  "PLAYERBANKSLOTS_CHANGED", "AUCTION_OWNED_LIST_UPDATE", "MAIL_INBOX_UPDATE" }
for _, e in ipairs(events) do safe(f.RegisterEvent, f, e) end

f:SetScript("OnEvent", function(_, event, arg1)
  if event == "ADDON_LOADED" then
    if arg1 == ADDON then db() end
  elseif event == "PLAYER_LOGIN" then
    safe(buildButton)
    if GameTooltip and GameTooltip.HookScript then safe(GameTooltip.HookScript, GameTooltip, "OnTooltipSetItem", onTooltipItem) end
    if C_Timer and C_Timer.After then
      C_Timer.After(4, function() safe(buildTab); safe(snapshot); safe(announceNew) end)
      C_Timer.After(8, function() safe(checkUpgrades) end)
      C_Timer.After(12, function() if ui.chat then safe(ensureDocked, ui.chat) end end)
      C_Timer.After(25, function() if ui.chat then safe(ensureDocked, ui.chat) end end)
    else
      safe(snapshot); safe(announceNew)
    end
  elseif event == "PLAYER_LOGOUT" then
    safe(snapshot)
  elseif event == "BANKFRAME_OPENED" then
    bankOpen = true; safe(scanBank)
  elseif event == "BANKFRAME_CLOSED" then
    safe(scanBank); bankOpen = false
  elseif event == "PLAYERBANKSLOTS_CHANGED" or event == "BAG_UPDATE_DELAYED" then
    if bankOpen then safe(scanBank) end
    if event == "BAG_UPDATE_DELAYED" then queueUpgrades() end
  elseif event == "AUCTION_OWNED_LIST_UPDATE" then
    safe(scanAuctions)
  elseif event == "MAIL_INBOX_UPDATE" then
    safe(scanMail)
  end
end)

SLASH_AHDESK1 = "/ahd"
SLASH_AHDESK2 = "/ahdesk"
SLASH_AHDESK3 = "/ah"
SlashCmdList["AHDESK"] = function(msg)
  msg = msg or ""
  local cmd = msg:lower():match("^%s*(%S*)") or ""
  if cmd == "" then
    toggle()
  elseif cmd == "sync" then
    snapshot(); ReloadUI()
  elseif cmd == "chat" then
    ui.chat = nil; safe(buildTab)
    if ui.chat then ensureDocked(ui.chat); say("chat tab ready", "claude") else DEFAULT_CHAT_FRAME:AddMessage(PREFIX .. "could not create the chat tab") end
  elseif cmd == "debug" then
    safe(scanSkills)
    local function has(n) return _G[n] and "yes" or "NO" end
    DEFAULT_CHAT_FRAME:AddMessage(PREFIX .. "GetNumSkillLines " .. has("GetNumSkillLines") .. ", GetSkillLineInfo " .. has("GetSkillLineInfo") ..
      ", GetNumTalentTabs " .. has("GetNumTalentTabs") .. ", GetTalentInfo " .. has("GetTalentInfo") ..
      ", C_SkillLine " .. (C_SkillLine and "yes" or "NO") .. ", C_ClassTalents " .. (C_ClassTalents and "yes" or "NO") ..
      ", C_SpecializationInfo " .. (C_SpecializationInfo and "yes" or "NO") .. ", GetProfessions " .. has("GetProfessions") .. ", C_Traits " .. (C_Traits and "yes" or "NO") ..
      ", C_TradeSkillUI " .. (C_TradeSkillUI and "yes" or "NO"))
    local c = char()
    DEFAULT_CHAT_FRAME:AddMessage(PREFIX .. "professions " .. #(c.professions or {}) .. ", talents " .. #((c.specs or {}).talents or {}) .. ", spec " .. tostring((c.specs or {}).activeName))
  elseif cmd == "status" then
    local c = char()
    DEFAULT_CHAT_FRAME:AddMessage(PREFIX .. string.format("bags %s, bank %s, auctions %s, outbox %d. Inbox built %s.",
      c.bagsAt and stamp(c.bagsAt) or "never", c.bankAt and stamp(c.bankAt) or "never (open the bank once)",
      c.auctionsAt and stamp(c.auctionsAt) or "never (open the Auctions tab)", #db().outbox,
      (AHDeskInbox and AHDeskInbox.built) and stamp(AHDeskInbox.built) or "none"))
  else
    send(msg)
    say(msg, "me")
    say("queued - Claude reads it after /reload (or /ahd sync)", "claude")
  end
end
