import os
import shutil


def test_stats():
    print("--- Testing Stats Logic ---")

    # 1. CPU
    try:
        load1, load5, load15 = os.getloadavg()
        cpu_count = os.cpu_count() or 1
        cpu_percent = min(100, round((load1 / cpu_count) * 100, 1))
        print(f"CPU: Load={load1}, Count={cpu_count}, Percent={cpu_percent}%")
    except Exception as e:
        print(f"CPU Error: {e}")

    # 2. RAM
    try:
        ram_total = 0
        ram_avail = 0
        with open("/proc/meminfo", "r") as f:
            for line in f:
                if "MemTotal" in line:
                    ram_total = int(line.split()[1]) * 1024
                elif "MemAvailable" in line:
                    ram_avail = int(line.split()[1]) * 1024

        ram_used = ram_total - ram_avail
        ram_percent = 0
        if ram_total > 0:
            ram_percent = round((ram_used / ram_total) * 100, 1)

        print(f"RAM: Total={ram_total}, Used={ram_used}, Percent={ram_percent}%")
    except Exception as e:
        print(f"RAM Error: {e}")

    # 3. Disk
    try:
        disk_usage = shutil.disk_usage("/srv/terreneitor")  # checking a specific path
        print(f"Disk: {disk_usage}")
    except Exception as e:
        print(f"Disk Error: {e}")

    # 4. Uptime
    try:
        with open("/proc/uptime", "r") as f:
            uptime_seconds = float(f.readline().split()[0])
        print(f"Uptime: {uptime_seconds}")
    except Exception as e:
        print(f"Uptime Error: {e}")


if __name__ == "__main__":
    test_stats()
