<#
    .SYNOPSIS
    This script will joing computer to domain
    .NOTES
    You need a Windows Server 2016 for this script to work.
#>

winrm quickconfig -q
winrm set winrm/config              '@{MaxTimeoutms="1800000"}'
winrm set winrm/config/winrs        '@{MaxMemoryPerShellMB="300"}'
winrm set winrm/config/service      '@{AllowUnencrypted="true"}'
winrm set winrm/config/service/auth '@{Basic="true"}'

# Requires -Version 3
# Requires -RunAsAdministrator
$dc_ip = "{{DC_IP}}"
$Domain = "{{DC_NAME}}"
$dc_admin = $Domain + "\Administrator"
$dc_password = ConvertTo-SecureString "{{DC_PASSWORD}}" -AsPlainText -Force
$creds = New-Object System.Management.Automation.PSCredential ($dc_admin, $dc_password)

# Configure DNS
$netid = Get-WmiObject -Class Win32_NetworkAdapter | select netconnectionid | foreach {$_.netconnectionid}
netsh interface ipv4 add dnsserver $netid $dc_ip index=1
$regPath = "HKLM:\System\CurrentControlSet\Services\TCPIP\Parameters"
Set-ItemProperty -Path $regPath -Name "SearchList" -Value $Domain -Confirm:$false

# Try to add to domain
Add-Computer -DomainName $Domain -Credential $creds -Restart -Force -Confirm:$false
