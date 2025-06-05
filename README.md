# Inventree-Plugin-QuickBarcode
QuickBarcode is a simple plugin for Inventree, that automatically can link the part IPN and serial of a stock item as barcode during part creation

## Description
When you create or edit a part or stock item in Inventree with QuickBarcode you can assign a custom barcode by just entering your barcode or qr code into the ipn field of the part or the serial of a stock item. This plugin will automatically link the barcode to your part so you can emedeately start to use it.

## Installation 
* clone into your plugins folder:

        git clone https://github.com/mtsonline/Inventree-Plugin-QuickBarcode

* after that restart Inventree to reinitialize the plugins.
* Aktivate Quick barcode.
* Activate event handlers for Plugins in the global plugin settings.
* Restart another time to load all settings correctly.
* Have a look at the plugin settings, you have to define an api key there, if you did not already put it into your .env file.    
You can create an api token at:
        https://your_site_url/admin/users/apitoken/add/

## usage
Quick Barcode will work in the background and assign ipn and serial automatically as barcode to your parts and stockitems.    
Please note, that at this time (v0.17.13 of Inventree) the event for stockitems does not work as documented and therefore assigning serial as barcode does only work when the stockitems are created or updated via the cli or via bulg import.    
I hope this will be fixed in an upcoming version.


Feel free to provide improvements or fixes. As this was my first plugin for Inventree there defenitely will be better ways to realize this functions, but I could not find an easier working way ;-)    
E.g. the internal /api solution was not working for me due to multiple issues with the docker setup and installing via the webinterface / pip did break some of the functions completely.
