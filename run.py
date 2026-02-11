from data.startup import wait_for_databases

print("Boot preflight checks...")
wait_for_databases()
print("Starting web server...")
