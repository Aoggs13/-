-- Paste into Roblox Studio Command Bar while NOT playing.
-- This installs the same six scripts as the tested native place.
assert(not game:GetService("RunService"):IsRunning(), "Stop Play before installing")
local rs=game:GetService("ReplicatedStorage")
local ss=game:GetService("ServerScriptService")
local sp=game:GetService("StarterPlayer")
assert(not rs:FindFirstChild("LavaRush"), "Lava Rush is already installed")
assert(not ss:FindFirstChild("LavaRushServer"), "Lava Rush is already installed")
local function add(class,name,parent,source)
 local obj=Instance.new(class); obj.Name=name
 if source then obj.Source=source end
 obj.Parent=parent; return obj
end
local shared=add("Folder","LavaRush",rs)
local remotes=add("Folder","Remotes",shared)
add("RemoteEvent","Action",remotes); add("RemoteEvent","Notice",remotes)
add("ModuleScript",[=[Rules]=],shared,[=[--!strict
-- Shared, deterministic rules. No Roblox services are needed to run this module.
local Rules = {
	RoundSeconds = 95,
	IntermissionSeconds = 12,
	CountdownSeconds = 5,
	StageCount = 24,
	StageRise = 3.6,
	CoinValue = 3,
	WinCoins = 30,
	SurvivalCoins = 5,
	MinSurvivalSeconds = 20,
	DashCooldown = 4,
	DashSpeed = 60,
	LavaStart = -6,
	LavaEnd = 89,
	LavaGraceSeconds = 12,
	MaxUpgradeLevel = 3,
}

local upgradeCosts = table.freeze({ 30, 65, 110 })

local function finite(value: number): boolean
	return value == value and math.abs(value) < math.huge
end

function Rules.lavaHeight(elapsed: number): number
	-- Keep the first twelve seconds safe, then rise to the summit over the round.
	if elapsed ~= elapsed then
		elapsed = 0
	end
	local progress = math.clamp(
		(elapsed - Rules.LavaGraceSeconds) / (Rules.RoundSeconds - Rules.LavaGraceSeconds),
		0,
		1
	)
	return Rules.LavaStart + (Rules.LavaEnd - Rules.LavaStart) * progress
end

function Rules.upgradeCost(level: number): number?
	-- A level denotes the upgrades already owned. Invalid levels cannot be bought.
	if not finite(level) or level < 0 or level >= Rules.MaxUpgradeLevel or level % 1 ~= 0 then
		return nil
	end
	return upgradeCosts[level + 1]
end

function Rules.walkSpeed(level: number): number
	if not finite(level) then
		level = 0
	end
	return 18 + 2 * math.clamp(math.floor(level), 0, Rules.MaxUpgradeLevel)
end

function Rules.canPurchase(balance: number, level: number): boolean
	local cost = Rules.upgradeCost(level)
	return finite(balance) and cost ~= nil and balance >= cost
end

function Rules.roundReward(escaped: boolean): number
	return if escaped then Rules.WinCoins else Rules.SurvivalCoins
end

function Rules.formatTime(seconds: number): string
	if not finite(seconds) then
		seconds = 0
	end
	local wholeSeconds = math.max(0, math.floor(seconds))
	return string.format("%d:%02d", math.floor(wholeSeconds / 60), wholeSeconds % 60)
end

return table.freeze(Rules)
]=])
add("ModuleScript",[=[GameState]=],shared,[=[--!strict
-- Server-owned progression and round settlement, independent of Roblox services.
local Rules = require(script.Parent:WaitForChild("Rules"))

local GameState = {}
GameState.__index = GameState

local function finite(value: any): boolean
	return type(value) == "number" and value == value and math.abs(value) < math.huge
end

local function integer(value: any, maximum: number): number
	if not finite(value) then
		return 0
	end
	return math.clamp(math.floor(value), 0, maximum)
end

local function time(value: number): number
	return if finite(value) then value else 0
end

function GameState.new()
	return setmetatable({
		profiles = {} :: { [number]: any },
		participants = {} :: { [number]: any },
		active = false,
	}, GameState)
end

function GameState.addPlayer(self: any, id: number, data: any?)
	if self.profiles[id] then
		return self.profiles[id]
	end
	local source = if type(data) == "table" then data else {}
	local profile = {
		Coins = integer(source.Coins, 1e9),
		Wins = integer(source.Wins, 1e9),
		SpeedLevel = integer(source.SpeedLevel, Rules.MaxUpgradeLevel),
		BestHeight = integer(source.BestHeight, 10000),
	}
	self.profiles[id] = profile
	return profile
end

function GameState.removePlayer(self: any, id: number)
	self.profiles[id] = nil
	self.participants[id] = nil
end

function GameState.startRound(self: any, ids: { number }, now: number)
	self.participants = {}
	self.active = true
	for _, id in ids do
		if self.profiles[id] then
			self.participants[id] = {
				Alive = true,
				Escaped = false,
				StartedAt = time(now),
				EndedAt = nil,
				Collected = {},
				DashReadyAt = 0,
			}
		end
	end
end

function GameState.getParticipant(self: any, id: number)
	return self.participants[id]
end

local function alive(self: any, id: number)
	local participant = self.participants[id]
	if self.active and self.profiles[id] and participant and participant.Alive then
		return participant
	end
	return nil
end

function GameState.eliminate(self: any, id: number, now: number): boolean
	local participant = alive(self, id)
	if not participant then
		return false
	end
	participant.Alive = false
	participant.EndedAt = time(now)
	return true
end

function GameState.escape(self: any, id: number, now: number): boolean
	local participant = alive(self, id)
	if not participant then
		return false
	end
	participant.Alive = false
	participant.Escaped = true
	participant.EndedAt = time(now)
	return true
end

function GameState.collect(self: any, id: number, key: any): boolean
	local participant = alive(self, id)
	if not participant or key == nil or participant.Collected[key] then
		return false
	end
	participant.Collected[key] = true
	local profile = self.profiles[id]
	profile.Coins = math.min(1e9, profile.Coins + Rules.CoinValue)
	return true
end

function GameState.dash(self: any, id: number, now: number): boolean
	local participant = alive(self, id)
	if not participant or not finite(now) or now < participant.DashReadyAt then
		return false
	end
	participant.DashReadyAt = now + Rules.DashCooldown
	return true
end

function GameState.upgrade(self: any, id: number): boolean
	local profile = self.profiles[id]
	if not profile or not Rules.canPurchase(profile.Coins, profile.SpeedLevel) then
		return false
	end
	local cost = Rules.upgradeCost(profile.SpeedLevel)
	assert(cost)
	profile.Coins -= cost
	profile.SpeedLevel += 1
	return true
end

function GameState.recordHeight(self: any, id: number, height: number)
	if not alive(self, id) or not finite(height) then
		return
	end
	local profile = self.profiles[id]
	profile.BestHeight = math.max(profile.BestHeight, integer(height, 10000))
end

function GameState.finishRound(self: any, now: number): { [number]: number }
	local rewards = {}
	if not self.active then
		return rewards
	end
	-- Settle once, even when finishRound is called twice by two server paths.
	self.active = false
	for id, participant in self.participants do
		local profile = self.profiles[id]
		if profile then
			local reward = 0
			if participant.Escaped then
				profile.Wins = math.min(1e9, profile.Wins + 1)
				reward = Rules.WinCoins
			elseif (participant.EndedAt or time(now)) - participant.StartedAt >= Rules.MinSurvivalSeconds then
				reward = Rules.SurvivalCoins
			end
			profile.Coins = math.min(1e9, profile.Coins + reward)
			rewards[id] = reward
		end
	end
	return rewards
end

return GameState
]=])
add("ModuleScript",[=[MapPlan]=],shared,[=[--!strict
-- A repeatable route keeps every jump fair while each seed changes the climb.
local Rules = require(script.Parent:WaitForChild("Rules"))

local MapPlan = {}

local function point(index: number, direction: number)
	local angle = math.rad(index * 30 * direction)
	return {
		X = math.sin(angle) * 20,
		Y = index * Rules.StageRise,
		Z = math.cos(angle) * 20,
	}
end

function MapPlan.generate(seed: number)
	if seed ~= seed or math.abs(seed) == math.huge then
		seed = 0
	end
	seed = math.floor(seed)
	local direction = if seed % 2 == 0 then 1 else -1
	local stages = {}
	for index = 1, Rules.StageCount do
		local position = point(index, direction)
		table.insert(stages, {
			X = position.X,
			Y = position.Y,
			Z = position.Z,
			Index = index,
			Size = 8,
			Fragile = index > 2 and index < Rules.StageCount - 1 and (index + seed % 5) % 5 == 0,
		})
	end
	local summit = point(Rules.StageCount + 1, direction)
	return {
		Stages = stages,
		Start = { X = 0, Y = 0, Z = 20, Size = 12 },
		Finish = { X = summit.X, Y = summit.Y, Z = summit.Z, Size = 12 },
		ThemeIndex = seed % 3 + 1,
	}
end

return table.freeze(MapPlan)
]=])
add("ModuleScript","ProfileStore",ss,[=[--!strict
-- Dependency-injected persistence with renewable session leases.
-- Callers choose retry timing; failed loads never authorize writes.
local ProfileStore = {}
ProfileStore.__index = ProfileStore

local LEASE_SECONDS = 180

local function finite(value: any): boolean
	return type(value) == "number" and value == value and math.abs(value) < math.huge
end

local function field(value: any, maximum: number): number
	return if finite(value) then math.clamp(math.floor(value), 0, maximum) else 0
end

local function snapshot(profile: any)
	local source = if type(profile) == "table" then profile else {}
	if next(source) == nil then
		return {}
	end
	return {
		Coins = field(source.Coins, 1e9),
		Wins = field(source.Wins, 1e9),
		SpeedLevel = field(source.SpeedLevel, 3),
		BestHeight = field(source.BestHeight, 10000),
	}
end

function ProfileStore.new(store: any, sessionId: string, nowFn: () -> number)
	assert(type(sessionId) == "string" and sessionId ~= "", "A nonempty session ID is required")
	return setmetatable({
		store = store,
		sessionId = sessionId,
		now = nowFn,
		owned = {} :: { [number]: boolean },
	}, ProfileStore)
end

function ProfileStore.load(self: any, id: number): (any, boolean)
	local now = self.now()
	local ok, result = pcall(function()
		return self.store:UpdateAsync("player_" .. tostring(id), function(record: any): any
			local existing = if type(record) == "table" then record else {}
			local owner = existing.SessionId
			local lease = existing.LeaseUntil
			if type(owner) == "string" and owner ~= "" and owner ~= self.sessionId
				and finite(lease) and lease > now then
				return nil
			end
			local data = if type(existing.Profile) == "table" then existing.Profile else existing
			return {
				Profile = snapshot(data),
				SessionId = self.sessionId,
				LeaseUntil = now + LEASE_SECONDS,
			}
		end)
	end)
	if not ok or type(result) ~= "table" or result.SessionId ~= self.sessionId then
		return nil, false
	end
	self.owned[id] = true
	return snapshot(result.Profile), true
end

function ProfileStore.save(self: any, id: number, profile: any, release: boolean?): boolean
	if not self.owned[id] then
		return false
	end
	local now = self.now()
	local copied = snapshot(profile)
	local ok, result = pcall(function()
		return self.store:UpdateAsync("player_" .. tostring(id), function(record: any): any
			if type(record) ~= "table" or record.SessionId ~= self.sessionId then
				return nil
			end
			return {
				Profile = copied,
				SessionId = if release then "" else self.sessionId,
				LeaseUntil = if release then 0 else now + LEASE_SECONDS,
			}
		end)
	end)
	local expectedOwner = if release then "" else self.sessionId
	if not ok or type(result) ~= "table" or result.SessionId ~= expectedOwner then
		return false
	end
	if release then
		self.owned[id] = nil
	end
	return true
end

return ProfileStore
]=])
add("Script","LavaRushServer",ss,[=[-- Lava Rush: authoritative rounds, economy and generated arena.
local Players = game:GetService("Players")
local ReplicatedStorage = game:GetService("ReplicatedStorage")
local RunService = game:GetService("RunService")
local DataStoreService = game:GetService("DataStoreService")
local Lighting = game:GetService("Lighting")
local ProfileStore = require(script.Parent:WaitForChild("ProfileStore"))

local shared = ReplicatedStorage:WaitForChild("LavaRush")
local Rules = require(shared:WaitForChild("Rules"))
local GameState = require(shared:WaitForChild("GameState"))
local MapPlan = require(shared:WaitForChild("MapPlan"))
local remotes = shared:WaitForChild("Remotes")
local action = remotes:WaitForChild("Action")
local notice = remotes:WaitForChild("Notice")
local engine = GameState.new()
local arena = Instance.new("Folder")
arena.Name = "LavaRushWorld"
arena.Parent = workspace
workspace.FallenPartsDestroyHeight = -70
Players.RespawnTime = 3

local phase = "Intermission"
local roundNumber = 0
local course = nil
local lava = nil
local roundStarted = 0
local shuttingDown = false
local loading = {}
local lastAction = {}
local lastStages = {}
local saveLocks = {}
local persistenceEnabled = game.GameId ~= 0 and not RunService:IsStudio()
local store = nil
local profiles = nil
if persistenceEnabled then
	local ok, result = pcall(function()
		return DataStoreService:GetDataStore("LavaRush_Profiles_v1")
	end)
	if ok then
		store = result
		profiles = ProfileStore.new(store, game.JobId, os.time)
	end
end

local themes = {
	{ Color3.fromRGB(43, 224, 188), Color3.fromRGB(48, 67, 87) },
	{ Color3.fromRGB(173, 142, 255), Color3.fromRGB(61, 50, 89) },
	{ Color3.fromRGB(255, 207, 93), Color3.fromRGB(73, 62, 49) },
}

local function part(name, size, position, color, parent, material)
	local item = Instance.new("Part")
	item.Name = name
	item.Size = size
	item.Position = position
	item.Color = color
	item.Material = material or Enum.Material.SmoothPlastic
	item.Anchored = true
	item.TopSurface = Enum.SurfaceType.Smooth
	item.BottomSurface = Enum.SurfaceType.Smooth
	item.Parent = parent
	return item
end

local function label(adornee, text, color, width, height)
	local gui = Instance.new("BillboardGui")
	gui.Size = UDim2.fromOffset(width or 260, height or 70)
	gui.StudsOffsetWorldSpace = Vector3.new(0, 5, 0)
	gui.AlwaysOnTop = false
	gui.MaxDistance = 180
	gui.Adornee = adornee
	gui.Parent = adornee
	local line = Instance.new("TextLabel")
	line.Size = UDim2.fromScale(1, 1)
	line.BackgroundTransparency = 1
	line.TextColor3 = color
	line.TextStrokeTransparency = 0.5
	line.Font = Enum.Font.GothamBold
	line.TextScaled = true
	line.Text = text
	line.Parent = gui
end

Lighting.ClockTime = 17.4
Lighting.Brightness = 2
Lighting.Ambient = Color3.fromRGB(115, 117, 148)
Lighting.OutdoorAmbient = Color3.fromRGB(130, 126, 159)
local atmosphere = Instance.new("Atmosphere")
atmosphere.Density = 0.25
atmosphere.Color = Color3.fromRGB(197, 178, 221)
atmosphere.Decay = Color3.fromRGB(88, 73, 114)
atmosphere.Parent = Lighting
local bloom = Instance.new("BloomEffect")
bloom.Intensity = 0.35
bloom.Size = 24
bloom.Threshold = 1.1
bloom.Parent = Lighting

-- Lobby stays clear of the lava and is separated from the course.
part("Lobby", Vector3.new(52, 3, 42), Vector3.new(106, 100, 0), Color3.fromRGB(30, 39, 55), arena)
local spawn = Instance.new("SpawnLocation")
spawn.Name = "LobbySpawn"
spawn.Size = Vector3.new(9, 0.7, 9)
spawn.Position = Vector3.new(106, 102, 5)
spawn.Anchored = true
spawn.Neutral = true
spawn.Duration = 0
spawn.Color = themes[1][1]
spawn.Material = Enum.Material.Neon
spawn.Parent = arena
label(spawn, "LAVA RUSH\nЛавадан қаш!", Color3.fromRGB(255, 214, 115), 320, 85)
for _, edge in ipairs({ {0, -21, 52, 1}, {0, 21, 52, 1}, {-26, 0, 1, 42}, {26, 0, 1, 42} }) do
	part("LobbyRail", Vector3.new(edge[3], 4, edge[4]), Vector3.new(106 + edge[1], 103, edge[2]), Color3.fromRGB(73, 97, 119), arena)
end
local board = part("RulesBoard", Vector3.new(28, 12, 1), Vector3.new(106, 109, -18), Color3.fromRGB(22, 29, 44), arena)
local boardGui = Instance.new("SurfaceGui")
boardGui.Face = Enum.NormalId.Back
boardGui.CanvasSize = Vector2.new(1000, 420)
boardGui.Parent = board
local boardText = Instance.new("TextLabel")
boardText.Size = UDim2.fromScale(0.94, 0.94)
boardText.Position = UDim2.fromScale(0.03, 0.03)
boardText.BackgroundTransparency = 1
boardText.TextColor3 = Color3.fromRGB(235, 241, 250)
boardText.Font = Enum.Font.GothamBold
boardText.TextSize = 47
boardText.TextWrapped = true
boardText.Text = "МҰНАРАНЫҢ ШЫҢЫНА ЖЕТ!\nКристалл: +3   •   Жеңіс: +30\nQ / X — серпіліс\nСары алаңдар уақытша құлайды!"
boardText.Parent = boardGui

local function sync(player)
	local profile = engine.profiles[player.UserId]
	if not profile then return end
	for _, key in ipairs({ "Coins", "Wins", "SpeedLevel", "BestHeight" }) do
		player:SetAttribute(key, profile[key])
	end
	local participant = engine:getParticipant(player.UserId)
	player:SetAttribute("InRound", engine.active and participant ~= nil and participant.Alive)
	player:SetAttribute("Escaped", participant ~= nil and participant.Escaped or false)
	player:SetAttribute("DashReadyAt", participant and participant.DashReadyAt or 0)
	local stats = player:FindFirstChild("leaderstats")
	if stats then
		stats.Coins.Value = profile.Coins
		stats.Wins.Value = profile.Wins
	end
	local character = player.Character
	local humanoid = character and character:FindFirstChildOfClass("Humanoid")
	if humanoid then humanoid.WalkSpeed = Rules.walkSpeed(profile.SpeedLevel) end
end

local function teleport(player, position)
	local character = player.Character
	local root = character and character:FindFirstChild("HumanoidRootPart")
	local humanoid = character and character:FindFirstChildOfClass("Humanoid")
	if root and humanoid and humanoid.Health > 0 then
		root.AssemblyLinearVelocity = Vector3.zero
		root.AssemblyAngularVelocity = Vector3.zero
		character:PivotTo(CFrame.new(position))
		return true
	end
	return false
end

local function touchedPlayer(hit)
	local character = hit:FindFirstAncestorOfClass("Model")
	return character and Players:GetPlayerFromCharacter(character)
end

local function save(player, release)
	if not profiles or player:GetAttribute("DataStatus") == "Session" then return end
	-- A leaving player must wait for an older autosave before taking a final snapshot.
	while saveLocks[player.UserId] do task.wait(0.1) end
	if not engine.profiles[player.UserId] then return end
	saveLocks[player.UserId] = true
	local ok = false
	for attempt = 1, 3 do
		local snapshot = table.clone(engine.profiles[player.UserId])
		ok = profiles:save(player.UserId, snapshot, release)
		if ok then break end
		task.wait(attempt)
	end
	if player.Parent then
		player:SetAttribute("DataStatus", if ok then "Saved" else "Retry")
		if not ok then notice:FireClient(player, "Сақтау уақытша істемейді. Қайта көреміз.") end
	end
	saveLocks[player.UserId] = nil
end

local function buildCourse(seed)
	if course then course:Destroy() end
	course = Instance.new("Folder")
	course.Name = "RoundCourse"
	course.Parent = arena
	local plan = MapPlan.generate(seed)
	local theme = themes[plan.ThemeIndex]
	part("ArenaFloor", Vector3.new(68, 2, 68), Vector3.new(0, -2, 0), Color3.fromRGB(35, 38, 51), course)
	-- Decorative mast and floating rings stay outside the route.
	part("Core", Vector3.new(7, 92, 7), Vector3.new(0, 43, 0), theme[2], course)
	for height = 0, 84, 14 do
		part("CoreLight", Vector3.new(7.2, 0.35, 7.2), Vector3.new(0, height, 0), theme[1], course, Enum.Material.Neon)
	end
	local start = part("Start", Vector3.new(12, 1, 12), Vector3.new(plan.Start.X, plan.Start.Y, plan.Start.Z), theme[1], course)
	label(start, "ЖОҒАРЫ! ↑", Color3.fromRGB(238, 255, 249), 160, 40)
	for _, stage in ipairs(plan.Stages) do
		local platform = part("Stage_" .. stage.Index, Vector3.new(stage.Size, 1, stage.Size), Vector3.new(stage.X, stage.Y, stage.Z), if stage.Fragile then Color3.fromRGB(255, 182, 77) else theme[2], course)
		part("Edge_" .. stage.Index, Vector3.new(stage.Size, 0.15, 0.3), platform.Position + Vector3.new(0, 0.57, stage.Size / 2 - 0.15), if stage.Fragile then Color3.fromRGB(255, 220, 121) else theme[1], course, Enum.Material.Neon).CanCollide = false
		if stage.Index % 4 == 0 then label(platform, tostring(stage.Index) .. " / " .. Rules.StageCount, theme[1], 110, 32) end
		local crumbling = false
		platform.Touched:Connect(function(hit)
			local player = touchedPlayer(hit)
			if phase ~= "Playing" or not player then return end
			local participant = engine:getParticipant(player.UserId)
			if not participant or not participant.Alive then return end
			local root = player.Character and player.Character:FindFirstChild("HumanoidRootPart")
			if not root or (root.Position - platform.Position).Magnitude > 12 then return end
			lastStages[player.UserId] = math.max(lastStages[player.UserId] or 0, stage.Index)
			if stage.Fragile and not crumbling then
				crumbling = true
				local thisRound = roundNumber
				task.delay(0.85, function()
					if thisRound ~= roundNumber or not platform.Parent then return end
					platform.CanCollide = false
					platform.Transparency = 0.85
					task.wait(2.3)
					if platform.Parent then
						platform.CanCollide = true
						platform.Transparency = 0
						crumbling = false
					end
				end)
			end
		end)
		local crystal = part("Crystal_" .. stage.Index, Vector3.new(1.5, 2.3, 1.5), platform.Position + Vector3.new(0, 2.6, 0), theme[1], course, Enum.Material.Neon)
		crystal.CanCollide = false
		crystal.CanTouch = true
		crystal.CFrame *= CFrame.Angles(0, math.pi / 4, math.pi / 8)
		crystal.Touched:Connect(function(hit)
			local player = touchedPlayer(hit)
			if phase ~= "Playing" or not player then return end
			local root = player.Character and player.Character:FindFirstChild("HumanoidRootPart")
			if not root or (root.Position - crystal.Position).Magnitude > 7 then return end
			if engine:collect(player.UserId, stage.Index) then
				sync(player)
				notice:FireClient(player, "+" .. Rules.CoinValue .. " кристалл!")
			end
		end)
	end
	local finish = part("Summit", Vector3.new(12, 1, 12), Vector3.new(plan.Finish.X, plan.Finish.Y, plan.Finish.Z), Color3.fromRGB(255, 210, 98), course, Enum.Material.Neon)
	label(finish, "★ МӘРЕ ★", Color3.fromRGB(255, 232, 161), 240, 65)
	for _, offset in ipairs({ Vector3.new(-3.5, 4, 0), Vector3.new(3.5, 4, 0), Vector3.new(0, 7.5, 0) }) do
		local gate = part("PortalFrame", if offset.X == 0 then Vector3.new(8, 1, 1) else Vector3.new(1, 7, 1), finish.Position + offset, themes[1][1], course, Enum.Material.Neon)
		gate.CanCollide = false
	end
	local field = part("Portal", Vector3.new(6, 6, 0.2), finish.Position + Vector3.new(0, 4, 0), themes[1][1], course, Enum.Material.Neon)
	field.CanCollide = false
	field.Transparency = 0.55
	finish.Touched:Connect(function(hit)
		local player = touchedPlayer(hit)
		if phase ~= "Playing" or not player or (lastStages[player.UserId] or 0) < Rules.StageCount then return end
		local root = player.Character and player.Character:FindFirstChild("HumanoidRootPart")
		if not root or (root.Position - finish.Position).Magnitude > 12 then return end
		if engine:escape(player.UserId, workspace:GetServerTimeNow()) then
			sync(player)
			teleport(player, spawn.Position + Vector3.new(0, 4, 0))
			notice:FireClient(player, "Шыңға жеттің! Раунд соңында +30 кристалл!")
		end
	end)
	lava = part("Lava", Vector3.new(74, 4, 74), Vector3.new(0, Rules.LavaStart - 2, 0), Color3.fromRGB(255, 76, 42), course, Enum.Material.Neon)
	lava.CanCollide = false
	lava.Transparency = 0.15
	-- Damage is evaluated by server height, not unreliable touch events.
	return plan
end

local function setPhase(value, seconds)
	phase = value
	shared:SetAttribute("Phase", value)
	shared:SetAttribute("SecondsLeft", seconds)
end

local function characterAdded(player, character)
	local humanoid = character:WaitForChild("Humanoid", 10)
	local root = character:WaitForChild("HumanoidRootPart", 10)
	if not humanoid or not root then return end
	humanoid.UseJumpPower = true
	humanoid.JumpPower = 50
	sync(player)
	humanoid.Died:Connect(function()
		if engine:eliminate(player.UserId, workspace:GetServerTimeNow()) then
			sync(player)
			notice:FireClient(player, "Келесі раундта тағы байқап көр!")
		end
	end)
	-- New joins and respawns wait in the safe lobby until the next round.
	teleport(player, spawn.Position + Vector3.new(0, 4, 0))
end

local function playerAdded(player)
	loading[player.UserId] = true
	player:SetAttribute("DataStatus", "Loading")
	player:SetAttribute("InRound", false)
	local stats = Instance.new("Folder")
	stats.Name = "leaderstats"
	stats.Parent = player
	for _, key in ipairs({ "Coins", "Wins" }) do
		local value = Instance.new("IntValue")
		value.Name = key
		value.Parent = stats
	end
	player.CharacterAdded:Connect(function(character) characterAdded(player, character) end)
	if player.Character then task.spawn(characterAdded, player, player.Character) end
	local data = nil
	local loaded = false
	if profiles then
		for attempt = 1, 3 do
			data, loaded = profiles:load(player.UserId)
			if loaded then break end
			task.wait(attempt)
		end
	end
	if not player.Parent then
		if loaded then profiles:save(player.UserId, data, true) end
		loading[player.UserId] = nil
		return
	end
	engine:addPlayer(player.UserId, data)
	player:SetAttribute("DataStatus", if loaded then "Saved" else "Session")
	loading[player.UserId] = nil
	sync(player)
	if not loaded then notice:FireClient(player, "Прогресс осы сессияда сақталады.") end
end

Players.PlayerAdded:Connect(playerAdded)
for _, player in ipairs(Players:GetPlayers()) do task.spawn(playerAdded, player) end
Players.PlayerRemoving:Connect(function(player)
	save(player, true)
	engine:removePlayer(player.UserId)
	loading[player.UserId] = nil
	lastAction[player.UserId] = nil
	lastStages[player.UserId] = nil
end)

-- Ignore unknown payloads. Prices, balances, participation and cooldowns are server-owned.
action.OnServerEvent:Connect(function(player, kind)
	if type(kind) ~= "string" or not engine.profiles[player.UserId] then return end
	local now = workspace:GetServerTimeNow()
	if now - (lastAction[player.UserId] or -math.huge) < 0.15 then return end
	lastAction[player.UserId] = now
	if kind == "Upgrade" then
		if engine:upgrade(player.UserId) then
			sync(player)
			notice:FireClient(player, "Жылдамдық жақсарды!")
		else
			notice:FireClient(player, "Кристалл жеткіліксіз немесе деңгей ең жоғары.")
		end
	elseif kind == "Dash" and phase == "Playing" then
		local root = player.Character and player.Character:FindFirstChild("HumanoidRootPart")
		local humanoid = player.Character and player.Character:FindFirstChildOfClass("Humanoid")
		if not root or not humanoid or humanoid.Health <= 0 then return end
		if engine:dash(player.UserId, now) then
			local facing = root.CFrame.LookVector
			local horizontal = Vector3.new(facing.X, 0, facing.Z)
			if horizontal.Magnitude > 0.01 then horizontal = horizontal.Unit end
			root.AssemblyLinearVelocity = horizontal * Rules.DashSpeed + Vector3.new(0, math.max(root.AssemblyLinearVelocity.Y, 16), 0)
			sync(player)
		end
	end
end)

local heartbeatTime = 0
RunService.Heartbeat:Connect(function(dt)
	heartbeatTime += dt
	if heartbeatTime < 0.1 or phase ~= "Playing" then return end
	heartbeatTime = 0
	local now = workspace:GetServerTimeNow()
	local height = Rules.lavaHeight(now - roundStarted)
	shared:SetAttribute("LavaHeight", height)
	if lava then lava.Position = Vector3.new(0, height - 2, 0) end
	for _, player in ipairs(Players:GetPlayers()) do
		local participant = engine:getParticipant(player.UserId)
		local root = player.Character and player.Character:FindFirstChild("HumanoidRootPart")
		local humanoid = player.Character and player.Character:FindFirstChildOfClass("Humanoid")
		if participant and participant.Alive and root and humanoid then
			-- Limit the arena: stepping out is elimination, not an escape from lava.
			if humanoid.Health <= 0 or root.Position.Y - 2 < height or math.abs(root.Position.X) > 42 or math.abs(root.Position.Z) > 42 then
				if engine:eliminate(player.UserId, now) then sync(player) end
				humanoid.Health = 0
			else
				engine:recordHeight(player.UserId, math.max(0, root.Position.Y - 3))
				player:SetAttribute("BestHeight", engine.profiles[player.UserId].BestHeight)
			end
		end
	end
end)

local function countdown(value, seconds)
	setPhase(value, seconds)
	for remaining = seconds, 1, -1 do
		if shuttingDown then return end
		shared:SetAttribute("SecondsLeft", remaining)
		task.wait(1)
	end
	shared:SetAttribute("SecondsLeft", 0)
end

shared:SetAttribute("RoundId", 0)
shared:SetAttribute("LavaHeight", Rules.LavaStart)
setPhase("Intermission", Rules.IntermissionSeconds)
buildCourse(1)

task.spawn(function()
	while not shuttingDown do
		countdown("Intermission", Rules.IntermissionSeconds)
		if shuttingDown then break end
		roundNumber += 1
		lastStages = {}
		local seed = math.random(1, 1000000)
		local plan = buildCourse(seed)
		shared:SetAttribute("Seed", seed)
		shared:SetAttribute("RoundId", roundNumber)
		shared:SetAttribute("LavaHeight", Rules.LavaStart)
		countdown("Countdown", Rules.CountdownSeconds)
		local contestants = {}
		for _, player in ipairs(Players:GetPlayers()) do
			if not loading[player.UserId] and engine.profiles[player.UserId] then
				if teleport(player, Vector3.new(plan.Start.X, plan.Start.Y + 4, plan.Start.Z)) then
					table.insert(contestants, player.UserId)
				end
			end
		end
		roundStarted = workspace:GetServerTimeNow()
		engine:startRound(contestants, roundStarted)
		setPhase("Playing", Rules.RoundSeconds)
		for _, player in ipairs(Players:GetPlayers()) do sync(player) end
		while not shuttingDown do
			local remaining = Rules.RoundSeconds - (workspace:GetServerTimeNow() - roundStarted)
			shared:SetAttribute("SecondsLeft", math.max(0, math.ceil(remaining)))
			local alive = 0
			for _, participant in pairs(engine.participants) do
				if participant.Alive then alive += 1 end
			end
			if remaining <= 0 or alive == 0 then break end
			task.wait(0.2)
		end
		local rewards = engine:finishRound(workspace:GetServerTimeNow())
		setPhase("Results", 6)
		for _, player in ipairs(Players:GetPlayers()) do
			sync(player)
			teleport(player, spawn.Position + Vector3.new(0, 4, 0))
			local reward = rewards[player.UserId]
			if reward and reward > 0 then notice:FireClient(player, "Раунд аяқталды: +" .. reward .. " кристалл!") end
			task.spawn(save, player)
		end
		countdown("Results", 6)
	end
end)

-- Autosave also catches purchases made between rounds.
task.spawn(function()
	while not shuttingDown do
		task.wait(60)
		for _, player in ipairs(Players:GetPlayers()) do task.spawn(save, player) end
	end
end)
game:BindToClose(function()
	shuttingDown = true
	local pending = 0
	for _, player in ipairs(Players:GetPlayers()) do
		pending += 1
		task.spawn(function() save(player, true); pending -= 1 end)
	end
	local deadline = os.clock() + 20
	while pending > 0 and os.clock() < deadline do task.wait(0.1) end
end)
]=])
add("LocalScript","LavaRushClient",sp:WaitForChild("StarterPlayerScripts"),[=[-- Lava Rush: presentation and input only. The server owns movement abilities and rewards.
local Players = game:GetService("Players")
local ReplicatedStorage = game:GetService("ReplicatedStorage")
local RunService = game:GetService("RunService")
local ContextActionService = game:GetService("ContextActionService")
local TweenService = game:GetService("TweenService")
local UserInputService = game:GetService("UserInputService")

local player = Players.LocalPlayer
local state = ReplicatedStorage:WaitForChild("LavaRush")
local Rules = require(state:WaitForChild("Rules"))
local remotes = state:WaitForChild("Remotes")
local action = remotes:WaitForChild("Action")
local notice = remotes:WaitForChild("Notice")

local C = {
	Background = Color3.fromRGB(17, 23, 33),
	Panel = Color3.fromRGB(24, 33, 45),
	Line = Color3.fromRGB(54, 68, 83),
	Text = Color3.fromRGB(243, 247, 251),
	Muted = Color3.fromRGB(164, 181, 198),
	Orange = Color3.fromRGB(255, 162, 68),
	Coral = Color3.fromRGB(255, 100, 89),
	Mint = Color3.fromRGB(115, 244, 204),
}

local function create(className, properties, parent)
	local object = Instance.new(className)
	for key, value in pairs(properties) do
		object[key] = value
	end
	object.Parent = parent
	return object
end

local function round(object, radius)
	create("UICorner", { CornerRadius = UDim.new(0, radius or 14) }, object)
end

local function outline(object)
	create("UIStroke", { Color = C.Line, Thickness = 1, Transparency = 0.15 }, object)
end

local function label(parent, text, position, size, fontSize, color, alignment)
	return create("TextLabel", {
		BackgroundTransparency = 1,
		Text = text,
		Position = position,
		Size = size,
		Font = Enum.Font.GothamMedium,
		TextSize = fontSize,
		TextColor3 = color or C.Text,
		TextXAlignment = alignment or Enum.TextXAlignment.Left,
		TextYAlignment = Enum.TextYAlignment.Center,
	}, parent)
end

local gui = create("ScreenGui", {
	Name = "LavaRushHUD",
	ResetOnSpawn = false,
	IgnoreGuiInset = false,
	DisplayOrder = 10,
	ZIndexBehavior = Enum.ZIndexBehavior.Sibling,
}, player:WaitForChild("PlayerGui"))

local top = create("Frame", {
	Name = "RoundPanel",
	AnchorPoint = Vector2.new(0.5, 0),
	Position = UDim2.new(0.5, 0, 0, 12),
	Size = UDim2.new(1, -24, 0, 101),
	BackgroundColor3 = C.Background,
	BackgroundTransparency = 0.04,
}, gui)
create("UISizeConstraint", { MaxSize = Vector2.new(960, 101) }, top)
local topScale = create("UIScale", { Scale = 1 }, top)
round(top, 17)
outline(top)
local accent = create("Frame", {
	Position = UDim2.fromOffset(15, 17), Size = UDim2.fromOffset(4, 34),
	BackgroundColor3 = C.Coral, BorderSizePixel = 0,
}, top)
round(accent, 2)
local title = label(top, "LAVA RUSH", UDim2.fromOffset(28, 13), UDim2.fromOffset(180, 28), 24)
title.Font = Enum.Font.GothamBlack
local subtitle = label(top, "ЛАВАДАН БИІК КӨТЕРІЛ", UDim2.fromOffset(29, 39), UDim2.fromOffset(210, 15), 10, C.Muted)
local phaseLabel = label(top, "КЕЛЕСІ РАУНД", UDim2.new(1, -156, 0, 14), UDim2.fromOffset(140, 17), 10, C.Muted, Enum.TextXAlignment.Right)
local timer = label(top, "0:00", UDim2.new(1, -124, 0, 29), UDim2.fromOffset(107, 30), 27, C.Orange, Enum.TextXAlignment.Right)
timer.Font = Enum.Font.GothamBold
create("Frame", { Position = UDim2.fromOffset(16, 66), Size = UDim2.new(1, -32, 0, 1), BackgroundColor3 = C.Line, BorderSizePixel = 0 }, top)
local coinsLabel = label(top, "◆  0", UDim2.fromOffset(17, 74), UDim2.new(0.32, -8, 0, 18), 13, C.Orange)
local winsLabel = label(top, "★  0 жеңіс", UDim2.new(0.34, 0, 0, 74), UDim2.new(0.35, -8, 0, 18), 12, C.Mint)
local saveLabel = label(top, "Жүктелуде", UDim2.new(0.7, 0, 0, 74), UDim2.new(0.3, -17, 0, 18), 10, C.Muted, Enum.TextXAlignment.Right)

local objective = create("Frame", {
	Name = "Objective", AnchorPoint = Vector2.new(0.5, 0),
	Position = UDim2.new(0.5, 0, 0, 122), Size = UDim2.new(1, -24, 0, 56),
	BackgroundColor3 = C.Panel, BackgroundTransparency = 0.1,
}, gui)
create("UISizeConstraint", { MaxSize = Vector2.new(560, 56) }, objective)
local objectiveScale = create("UIScale", { Scale = 1 }, objective)
round(objective, 12)
local objectiveText = label(objective, "Келесі раундқа дайындал!", UDim2.fromOffset(13, 7), UDim2.new(1, -26, 0, 22), 12)
objectiveText.TextScaled = true
create("UITextSizeConstraint", { MinTextSize = 8, MaxTextSize = 12 }, objectiveText)
local track = create("Frame", { Position = UDim2.fromOffset(13, 39), Size = UDim2.new(1, -26, 0, 5), BackgroundColor3 = C.Line, BorderSizePixel = 0, ClipsDescendants = true }, objective)
round(track, 3)
local progress = create("Frame", { Size = UDim2.fromScale(0, 1), BackgroundColor3 = C.Mint, BorderSizePixel = 0 }, track)
round(progress, 3)

local controls = create("Frame", {
	Name = "Actions", AnchorPoint = Vector2.new(0.5, 1), Position = UDim2.new(0.5, 0, 1, -24),
	Size = UDim2.fromOffset(370, 98), BackgroundTransparency = 1,
}, gui)
local controlsScale = create("UIScale", { Scale = 1 }, controls)
local dash = create("TextButton", {
	Name = "Dash", Position = UDim2.fromOffset(0, 0), Size = UDim2.fromOffset(168, 64),
	BackgroundColor3 = C.Mint, TextColor3 = C.Background, Text = "СЕРПІЛУ  [Q / X]",
	TextSize = 13, Font = Enum.Font.GothamBold, AutoButtonColor = true,
}, controls)
round(dash, 14)
local upgrade = create("TextButton", {
	Name = "Upgrade", Position = UDim2.fromOffset(180, 0), Size = UDim2.fromOffset(190, 64),
	BackgroundColor3 = C.Panel, TextColor3 = C.Orange, Text = "ЖЫЛДАМДЫҚ +",
	TextSize = 12, Font = Enum.Font.GothamBold, AutoButtonColor = true,
}, controls)
round(upgrade, 14)
outline(upgrade)
local abilityHint = label(controls, "WASD — жүру  •  SPACE — секіру", UDim2.fromOffset(0, 71), UDim2.fromOffset(370, 19), 10, C.Muted, Enum.TextXAlignment.Center)

local toast = create("Frame", {
	Name = "Notice", AnchorPoint = Vector2.new(0.5, 0), Position = UDim2.new(0.5, 0, 0, 189),
	Size = UDim2.new(1, -36, 0, 48), BackgroundColor3 = C.Background,
	BackgroundTransparency = 0.04, Visible = false,
}, gui)
create("UISizeConstraint", { MaxSize = Vector2.new(500, 65) }, toast)
local toastScale = create("UIScale", { Scale = 1 }, toast)
round(toast, 12)
outline(toast)
local toastText = label(toast, "", UDim2.fromOffset(12, 5), UDim2.new(1, -24, 1, -10), 13, C.Mint, Enum.TextXAlignment.Center)
toastText.TextWrapped = true
local toastVersion = 0
local function showNotice(message)
	toastVersion += 1
	local version = toastVersion
	toastText.Text = tostring(message)
	toast.Visible = true
	toast.BackgroundTransparency = 0.04
	task.delay(3.8, function()
		if version == toastVersion then
			local tween = TweenService:Create(toast, TweenInfo.new(0.2), { BackgroundTransparency = 1 })
			tween:Play()
			tween.Completed:Wait()
			if version == toastVersion then toast.Visible = false end
		end
	end)
end
notice.OnClientEvent:Connect(showNotice)

local phaseNames = {
	Intermission = "КЕЛЕСІ РАУНД", Countdown = "ДАЙЫНДАЛ", Playing = "ЛАВА КӨТЕРІЛУДЕ", Results = "РАУНД АЯҚТАЛДЫ",
}
local function numberAttribute(name, default)
	local value = player:GetAttribute(name)
	return if typeof(value) == "number" then value else default
end

local function refresh()
	local phase = state:GetAttribute("Phase") or "Intermission"
	phaseLabel.Text = phaseNames[phase] or "LAVA RUSH"
	timer.Text = Rules.formatTime(state:GetAttribute("SecondsLeft") or 0)
	timer.TextColor3 = if phase == "Playing" and (state:GetAttribute("SecondsLeft") or 0) < 15 then C.Coral else C.Orange
	local coins = numberAttribute("Coins", 0)
	local level = numberAttribute("SpeedLevel", 0)
	coinsLabel.Text = "◆  " .. tostring(coins)
	winsLabel.Text = "★  " .. tostring(numberAttribute("Wins", 0)) .. " жеңіс"
	local status = player:GetAttribute("DataStatus")
	saveLabel.Text = if status == "Saved" then "Дерек сақталады" elseif status == "Loading" then "Жүктелуде" elseif status == "Retry" then "Сақтау күтілуде" else "Осы сессияда"
	local cost = Rules.upgradeCost(level)
	if cost then
		upgrade.Text = "ЖЫЛДАМДЫҚ +" .. tostring(level + 1) .. "\n◆ " .. tostring(cost) .. "  ·  " .. tostring(Rules.walkSpeed(level + 1)) .. " жылдамдық"
		upgrade.TextColor3 = if coins >= cost then C.Orange else C.Muted
	else
		upgrade.Text = "ЖЫЛДАМДЫҚ MAX\n" .. tostring(Rules.walkSpeed(level)) .. " жылдамдық"
		upgrade.TextColor3 = C.Mint
	end
	if player:GetAttribute("Escaped") then
		objectiveText.Text = "МӘРЕ! +" .. tostring(Rules.WinCoins) .. " кристалл. Келесі раундты күт."
	elseif player:GetAttribute("InRound") and phase == "Playing" then
		objectiveText.Text = "Жоғарыдағы жасыл порталға жет! Кристалдарды жина."
	elseif phase == "Countdown" then
		objectiveText.Text = "Стартқа дайындал! Жол әр раундта өзгереді."
	elseif phase == "Playing" then
		objectiveText.Text = "Лоббидесің. Келесі раундқа автоматты қосыласың."
	else
		objectiveText.Text = "Келесі раундқа дайындал! Лоббиде жаттығуға болады."
	end
end

local function requestDash()
	if UserInputService:GetFocusedTextBox() then return end
	if player:GetAttribute("InRound") and state:GetAttribute("Phase") == "Playing" then
		action:FireServer("Dash")
	end
end

dash.Activated:Connect(requestDash)
upgrade.Activated:Connect(function()
	if Rules.upgradeCost(numberAttribute("SpeedLevel", 0)) then
		action:FireServer("Upgrade")
	end
end)
ContextActionService:BindAction("LavaRushDash", function(_, inputState)
	if inputState == Enum.UserInputState.Begin then requestDash() end
	return Enum.ContextActionResult.Pass
end, false, Enum.KeyCode.Q, Enum.KeyCode.ButtonX)

for _, attribute in ipairs({ "Phase", "SecondsLeft", "RoundId" }) do
	state:GetAttributeChangedSignal(attribute):Connect(refresh)
end
for _, attribute in ipairs({ "Coins", "Wins", "SpeedLevel", "BestHeight", "InRound", "Escaped", "DataStatus" }) do
	player:GetAttributeChangedSignal(attribute):Connect(refresh)
end

local shade = create("Frame", {
	Name = "Welcome", Size = UDim2.fromScale(1, 1), BackgroundColor3 = Color3.fromRGB(5, 10, 18),
	BackgroundTransparency = 0.2, Active = true, ZIndex = 20,
}, gui)
local welcome = create("Frame", {
	AnchorPoint = Vector2.new(0.5, 0.5), Position = UDim2.fromScale(0.5, 0.5),
	Size = UDim2.fromOffset(450, 368), BackgroundColor3 = C.Background, ZIndex = 21,
}, shade)
round(welcome, 22)
outline(welcome)
local welcomeScale = create("UIScale", { Scale = 1 }, welcome)
local welcomeTitle = label(welcome, "ЛАВАДАН ҚАШ!", UDim2.fromOffset(27, 26), UDim2.fromOffset(396, 44), 31, C.Orange)
welcomeTitle.Font = Enum.Font.GothamBlack
welcomeTitle.ZIndex = 22
local welcomeIntro = label(welcome, "Биікке өрмеле. Порталға жет. Қайта жең.", UDim2.fromOffset(28, 76), UDim2.fromOffset(394, 24), 14, C.Muted)
welcomeIntro.ZIndex = 22
local helpText = label(welcome,
	"01   Алғашқы 12 секундта дайындал. Сосын лава көтеріледі!\n\n02   Сары платформалар құлайды! Кідірмей секір.\n\n03   Кристалл жина, жылдамдығыңды жақсарт. Q / X — серпілу.\n\n04   Телефонда батырманы бас. Құласаң, жаңа раундты күт.",
	UDim2.fromOffset(28, 115), UDim2.fromOffset(394, 160), 13, C.Text)
helpText.TextWrapped = true
helpText.TextYAlignment = Enum.TextYAlignment.Top
helpText.ZIndex = 22
local play = create("TextButton", {
	Position = UDim2.fromOffset(27, 294), Size = UDim2.fromOffset(396, 49),
	BackgroundColor3 = C.Mint, Text = "ОЙНАЙЫҚ!", TextColor3 = C.Background,
	TextSize = 16, Font = Enum.Font.GothamBold, ZIndex = 22,
}, welcome)
round(play, 13)
play.Activated:Connect(function() shade.Visible = false end)

local function responsive()
	local camera = workspace.CurrentCamera
	if not camera then return end
	local viewport = camera.ViewportSize
	welcomeScale.Scale = math.min(1, (viewport.X - 24) / 450, (viewport.Y - 40) / 368)
	local mobile = UserInputService.TouchEnabled
	local shortScreen = viewport.Y < 520
	-- 101 * .72 + 6, then 56 * .72 + 84: the objective ends at 125px.
	topScale.Scale = if shortScreen then 0.72 else 1
	objectiveScale.Scale = if shortScreen then 0.72 else 1
	toastScale.Scale = if shortScreen then 0.8 else 1
	top.Position = UDim2.new(0.5, 0, 0, if shortScreen then 6 else 12)
	objective.Position = UDim2.new(0.5, 0, 0, if shortScreen then 84 else 122)
	toast.Position = UDim2.new(0.5, 0, 0, if shortScreen then 132 else 189)
	controlsScale.Scale = math.min(1, (viewport.X - 32) / 370)
	if mobile and shortScreen and viewport.X > viewport.Y then
		-- Keep the centre buttons between the native controls in landscape.
		controlsScale.Scale = math.min(0.8, math.max(0.62, (viewport.X - 240) / 370))
		controls.Position = UDim2.new(0.5, 0, 1, -18)
		abilityHint.Text = "Экрандағы басқару — жүру және секіру"
	elseif mobile then
		-- Above the native joystick and jump controls, retaining their touch zones.
		controls.Position = UDim2.new(0.5, 0, 1, -139)
		abilityHint.Text = "Экрандағы басқару — жүру және секіру"
	else
		controls.Position = UDim2.new(0.5, 0, 1, -18)
		abilityHint.Text = "WASD — жүру  •  SPACE — секіру"
	end
	if viewport.X < 430 then
		title.TextSize = 20
		subtitle.TextSize = 8
		subtitle.Size = UDim2.fromOffset(180, 15)
		phaseLabel.TextSize = 8
		phaseLabel.Size = UDim2.fromOffset(113, 17)
		phaseLabel.Position = UDim2.new(1, -130, 0, 14)
	else
		title.TextSize = 24
		subtitle.TextSize = 10
		subtitle.Size = UDim2.fromOffset(210, 15)
		phaseLabel.TextSize = 10
		phaseLabel.Size = UDim2.fromOffset(140, 17)
		phaseLabel.Position = UDim2.new(1, -156, 0, 14)
	end
end
local cameraConnection
local function watchCamera()
	if cameraConnection then cameraConnection:Disconnect() end
	if workspace.CurrentCamera then
		cameraConnection = workspace.CurrentCamera:GetPropertyChangedSignal("ViewportSize"):Connect(responsive)
	end
	responsive()
end
workspace:GetPropertyChangedSignal("CurrentCamera"):Connect(watchCamera)
watchCamera()

local elapsed = 0
RunService.RenderStepped:Connect(function(dt)
	elapsed += dt
	if elapsed < 0.1 then return end
	elapsed = 0
	local remaining = math.max(0, numberAttribute("DashReadyAt", 0) - workspace:GetServerTimeNow())
	local active = player:GetAttribute("InRound") and state:GetAttribute("Phase") == "Playing"
	if not active then
		dash.Text = "СЕРПІЛУ\nРаундта қолжетімді"
		dash.BackgroundColor3 = C.Panel
		dash.TextColor3 = C.Muted
	elseif remaining > 0 then
		dash.Text = "СЕРПІЛУ\n" .. string.format("%.1f с", remaining)
		dash.BackgroundColor3 = C.Panel
		dash.TextColor3 = C.Muted
	else
		dash.Text = "СЕРПІЛУ  [Q / X]"
		dash.BackgroundColor3 = C.Mint
		dash.TextColor3 = C.Background
	end
	local character = player.Character
	local root = character and character:FindFirstChild("HumanoidRootPart")
	local height = if active and root then root.Position.Y else 0
	if player:GetAttribute("Escaped") then height = Rules.StageCount * Rules.StageRise end
	progress.Size = UDim2.fromScale(math.clamp(height / (Rules.StageCount * Rules.StageRise), 0, 1), 1)
end)
refresh()
]=])
sp.CameraMinZoomDistance=5; sp.CameraMaxZoomDistance=70
sp.CharacterWalkSpeed=18; sp.CharacterJumpPower=50; sp.CharacterUseJumpPower=true
print("LAVA RUSH installed. Press Play/F5.")
