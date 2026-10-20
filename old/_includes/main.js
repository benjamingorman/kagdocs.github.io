var sidebar = document.getElementById('sidebar'),
	categories = sidebar.querySelectorAll('h6');

// Toggle folding for one category header
function toggleFold(h6)
{
	var ul = h6.nextElementSibling;

	if (ul.style.display == "none")
	{
		h6.classList.remove("folded");
		ul.style.display = "block";
	}
	else
	{
		h6.classList.add("folded");
		ul.style.display = "none";
	}
}

// Toggle all category headers but the first one
for (i = 1; i < categories.length; i++)
{
	toggleFold(categories[i]);
}

sidebar.addEventListener("click", function(event)
{
	if (event.target.nodeName == "H6")
		toggleFold(event.target);
});
