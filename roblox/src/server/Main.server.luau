-- Lava Rush: authoritative rounds, economy and generated arena.
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
