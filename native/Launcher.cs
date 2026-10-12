using System;
using System.Diagnostics;
using System.IO;
using System.Windows.Forms;
using System.Security.Cryptography;
using System.Text;

// Small Windows launcher; inference stays in the shipped isolated runtime.
class Launcher {
    static string Quote(string value) {
        var result = new StringBuilder("\""); int slashes = 0;
        foreach (char c in value) {
            if (c == '\\') { slashes++; continue; }
            result.Append('\\', c == '"' ? slashes * 2 + 1 : slashes);
            result.Append(c); slashes = 0;
        }
        result.Append('\\', slashes * 2); result.Append('"');
        return result.ToString();
    }
    [STAThread] static int Main(string[] args) {
        try {
            if (args.Length == 6 && args[0] == "--apply-update") {
                string installer = args[1], expected = args[2], target = args[4];
                int pid = int.Parse(args[3]);
                try { using (var old = Process.GetProcessById(pid)) {
                    if (!old.WaitForExit(120000)) throw new IOException("App chưa đóng; cập nhật được hoãn để giữ dữ liệu.");
                }} catch (ArgumentException) { }
                int parentPid = int.Parse(args[5]);
                if (parentPid > 0) try { using (var old = Process.GetProcessById(parentPid)) {
                    if (!old.WaitForExit(120000)) throw new IOException("Launcher cũ chưa đóng; chưa cài cập nhật.");
                }} catch (ArgumentException) { }
                using (var sha = SHA256.Create()) using (var file = File.OpenRead(installer)) {
                    string hash = BitConverter.ToString(sha.ComputeHash(file)).Replace("-", "").ToLowerInvariant();
                    if (hash != expected) throw new IOException("Bộ cài đã thay đổi; không chạy cập nhật.");
                }
                var install = new ProcessStartInfo(installer, "/SILENT /SUPPRESSMSGBOXES /NORESTART /DIR=" + Quote(target));
                install.UseShellExecute = true;
                using (var setup = Process.Start(install)) {
                    setup.WaitForExit();
                    if (setup.ExitCode != 0) throw new IOException("Cài cập nhật chưa hoàn tất (mã " + setup.ExitCode + ").");
                }
                Process.Start(Path.Combine(target, "ReupVoiceStudio.exe"));
                return 0;
            }
            string root = AppDomain.CurrentDomain.BaseDirectory;
            string python = Path.Combine(root, "runtime", "pythonw.exe");
            if (!File.Exists(python) && !File.Exists(Path.Combine(root, "installed.flag")))
                python = Path.Combine(root, ".venv", "Scripts", "pythonw.exe");
            // Developer checkout fallback, never used by an installed build.
            if (!File.Exists(python) && !File.Exists(Path.Combine(root, "installed.flag")))
                python = Path.GetFullPath(Path.Combine(root, "..", "MoneyPrinterTurbo", ".venv", "Scripts", "pythonw.exe"));
            if (!File.Exists(python) && !File.Exists(Path.Combine(root, "installed.flag")))
                python = Path.GetFullPath(Path.Combine(root, "..", "release", "MPT", "MoneyPrinterTurbo", "runtime", "pythonw.exe"));
            if (args.Length == 1 && args[0] == "--print-runtime") { File.WriteAllText(Path.Combine(root,"launcher-runtime.txt"),python,Encoding.UTF8); return 0; }
            if (!File.Exists(python)) throw new IOException("Thiếu runtime\\pythonw.exe. Vui lòng cài lại ứng dụng.");
            string command = "-I " + Quote(Path.Combine(root, "launcher.py"));
            foreach (string arg in args) command += " " + Quote(arg);
            var start = new ProcessStartInfo(python, command);
            start.WorkingDirectory = root;
            start.UseShellExecute = false;
            start.CreateNoWindow = true;
            start.EnvironmentVariables.Remove("PYTHONHOME");
            start.EnvironmentVariables.Remove("PYTHONPATH");
            start.EnvironmentVariables["REUP_LAUNCHER_PID"] = Process.GetCurrentProcess().Id.ToString();
            using (Process child = Process.Start(start)) {
                child.WaitForExit();
                return child.ExitCode;
            }
        } catch (Exception error) {
            MessageBox.Show(error.Message, "Reup Voice Studio", MessageBoxButtons.OK, MessageBoxIcon.Error);
            return 1;
        }
    }
}
