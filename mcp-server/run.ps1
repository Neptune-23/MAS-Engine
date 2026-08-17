param (
    [string]$projectPath,
    [string]$description = "分析项目结构，推理构建步骤，然后执行构建"
)

# 如果运行命令时没带路径参数，就弹出提示让你现场输入
if (-not $projectPath) {
    $inputPath = Read-Host "请输入项目路径 (例如: D:/test_node_project)"
    if ($inputPath -and $inputPath.Trim() -ne "") {
        $projectPath = $inputPath.Trim()
    } else {
        Write-Host "❌ 未指定项目路径，已退出。"
        exit 1
    }
}

$task = "分析 $projectPath $description"
$command = "python server.py --standalone --task `"$task`""

Write-Host "🚀 启动 MAS-Engine 独立模式"
Write-Host "📋 任务: $task"
Invoke-Expression $command