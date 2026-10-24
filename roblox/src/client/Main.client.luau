-- Lava Rush: presentation and input only. The server owns movement abilities and rewards.
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
