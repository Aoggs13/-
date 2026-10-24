local ProfileStore = require("../src/server/ProfileStore")

local passed = 0
local function test(name, run)
	local ok, problem = pcall(run)
	if not ok then
		error(name .. ": " .. tostring(problem), 0)
	end
	passed += 1
	print("PASS " .. name)
end

local function fixture()
	local clock = { value = 1000 }
	local store = { records = {}, fail = false, calls = 0 }
	function store:UpdateAsync(key, callback)
		self.calls += 1
		if self.fail then
			error("datastore unavailable")
		end
		local replacement = callback(self.records[key])
		if replacement ~= nil then
			self.records[key] = replacement
		end
		return replacement
	end
	local function now()
		return clock.value
	end
	return store, clock, ProfileStore.new(store, "server-a", now), ProfileStore.new(store, "server-b", now)
end

test("fresh load claims a renewable lease and returns an empty profile", function()
	local store, clock, owner = fixture()
	local data, ok = owner:load(1)
	assert(ok and next(data) == nil)
	assert(store.records.player_1.SessionId == "server-a")
	assert(store.records.player_1.LeaseUntil == 1180)
	clock.value = 1060
	assert(owner:save(1, { Coins = 25, Wins = 1, SpeedLevel = 2, BestHeight = 75 }))
	assert(store.records.player_1.Profile.Coins == 25)
	assert(store.records.player_1.LeaseUntil == 1240)
end)

test("an unexpired foreign lease blocks load and cannot authorize later saves", function()
	local store, _, first, second = fixture()
	assert(select(2, first:load(1)))
	local data, ok = second:load(1)
	assert(data == nil and not ok)
	local beforeCalls = store.calls
	assert(not second:save(1, { Coins = 999 }))
	assert(store.calls == beforeCalls)
	assert(store.records.player_1.SessionId == "server-a")
	assert(store.records.player_1.Profile.Coins == nil)
end)

test("a failed load remains session-only and cannot overwrite existing data", function()
	local store, _, owner = fixture()
	store.fail = true
	local data, ok = owner:load(1)
	assert(data == nil and not ok)
	store.fail = false
	store.records.player_1 = { Coins = 83 }
	assert(not owner:save(1, { Coins = 0 }))
	assert(store.records.player_1.Coins == 83)
end)

test("expired leases may be taken over, and a stale owner cannot write", function()
	local store, clock, first, second = fixture()
	assert(select(2, first:load(1)))
	assert(first:save(1, { Coins = 91 }))
	clock.value = 1180
	local data, ok = second:load(1)
	assert(ok and data.Coins == 91)
	assert(store.records.player_1.SessionId == "server-b")
	assert(not first:save(1, { Coins = 0 }))
	assert(not first:save(1, { Coins = 0 }, true))
	assert(store.records.player_1.Profile.Coins == 91)
	assert(store.records.player_1.SessionId == "server-b")
end)

test("release permits immediate reacquisition and removes the old write permission", function()
	local store, _, first, second = fixture()
	assert(select(2, first:load(1)))
	assert(first:save(1, { Coins = 51, Wins = 2 }, true))
	assert(store.records.player_1.SessionId == "" and store.records.player_1.LeaseUntil == 0)
	assert(not first:save(1, { Coins = 99 }))
	local data, ok = second:load(1)
	assert(ok and data.Coins == 51 and data.Wins == 2)
end)

test("failed saves and releases retain ownership for retry", function()
	local store, _, owner = fixture()
	assert(select(2, owner:load(1)))
	store.fail = true
	assert(not owner:save(1, { Coins = 12 }))
	assert(not owner:save(1, { Coins = 12 }, true))
	store.fail = false
	assert(owner:save(1, { Coins = 12 }))
	assert(store.records.player_1.Profile.Coins == 12)
	assert(owner:save(1, { Coins = 13 }, true))
	assert(store.records.player_1.Profile.Coins == 13)
end)

test("legacy flat profiles migrate and unrelated fields are never persisted", function()
	local store, _, owner = fixture()
	store.records.player_1 = { Coins = 71, Wins = 4, SpeedLevel = 1, BestHeight = 62, Extra = "discard" }
	local data, ok = owner:load(1)
	assert(ok and data.Coins == 71 and data.Wins == 4)
	assert(data.SpeedLevel == 1 and data.BestHeight == 62 and data.Extra == nil)
	assert(store.records.player_1.Profile.Extra == nil)
	assert(store.records.player_1.SessionId == "server-a")
end)

test("load and save return independent snapshots and never mutate existing records", function()
	local store, _, owner = fixture()
	local old = { Profile = { Coins = 8 }, SessionId = "", LeaseUntil = 0 }
	store.records.player_1 = old
	local data, ok = owner:load(1)
	assert(ok)
	assert(old.SessionId == "" and old.Profile.Coins == 8)
	data.Coins = 50
	assert(store.records.player_1.Profile.Coins == 8)
	assert(owner:save(1, data))
	data.Coins = 999
	assert(store.records.player_1.Profile.Coins == 50)
end)

test("malformed fields are normalized to safe persistence values", function()
	local store, _, owner = fixture()
	store.records.player_1 = { Coins = 2e9, Wins = -1, SpeedLevel = 8, BestHeight = math.huge }
	local data, ok = owner:load(1)
	assert(ok and data.Coins == 1e9 and data.Wins == 0)
	assert(data.SpeedLevel == 3 and data.BestHeight == 0)
end)

test("a successful pcall with no claimed result does not establish ownership", function()
	local store = {}
	function store:UpdateAsync(_key, _callback)
		return nil
	end
	local owner = ProfileStore.new(store, "server-a", function() return 1000 end)
	assert(not select(2, owner:load(1)))
	assert(not owner:save(1, { Coins = 99 }))
end)

print(string.format("%d profile-store tests passed", passed))
